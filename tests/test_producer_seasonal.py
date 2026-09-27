"""The producer shifts live temp/humidity along the seasonal curve (D52, FR-H3)."""

import csv
from datetime import datetime, timezone

import pytest

from producer import replay, seasonal, synthetic
from producer.device_stats import compute_baseline_stats
from producer.state import ProducerState

JANUARY = datetime(2026, 1, 13, 12, tzinfo=timezone.utc)
JULY = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def frozen(at):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at
    return Frozen


class FakePublisher:
    def __init__(self):
        self.events = []

    def publish(self, topic, event, key=None):
        self.events.append(event)


class NoWait:
    def wait_for_next_tick(self):
        pass


@pytest.fixture
def stats(source_csv):
    return compute_baseline_stats(str(source_csv))


def replay_at(at, source_csv, stats, monkeypatch, row_limit=30):
    monkeypatch.setattr(replay, "datetime", frozen(at))
    publisher = FakePublisher()
    replay.run_replay(csv_path=str(source_csv), row_limit=row_limit, stats=stats, publisher=publisher,
                      topic="t", rate_limiter=NoWait(), state=ProducerState(100, "t"))
    return publisher.events


def test_replay_shifts_temp_and_humidity_by_event_time(source_csv, stats, monkeypatch):
    events = replay_at(JANUARY, source_csv, stats, monkeypatch)
    with open(source_csv, newline="", encoding="utf-8") as f:
        source = list(csv.DictReader(f))[-30:]
    assert len(events) == 30
    for event, row in zip(events, source):
        assert event["temp"] == pytest.approx(float(row["temp"]) + seasonal.offset("temp", JANUARY))
        assert event["humidity"] == pytest.approx(seasonal.apply("humidity", float(row["humidity"]), JANUARY))
        assert event["co"] == pytest.approx(float(row["co"]))  # not seasonal
        assert event["source_ts"].startswith("2020-07-")      # provenance kept
        assert event["event_ts"].startswith("2026-01-13")


def test_replay_in_july_passes_values_through(source_csv, stats, monkeypatch):
    events = replay_at(JULY, source_csv, stats, monkeypatch, row_limit=5)
    with open(source_csv, newline="", encoding="utf-8") as f:
        source = list(csv.DictReader(f))[-5:]
    assert [e["temp"] for e in events] == pytest.approx([float(r["temp"]) for r in source], abs=0.05)


def test_synthetic_events_follow_the_season(stats, monkeypatch):
    def mean_temp(at):
        monkeypatch.setattr(synthetic, "datetime", frozen(at))
        gen = synthetic.SyntheticGenerator(stats, anomaly_probability=0.0, anomaly_sigma_multiplier=4.0)
        temps = [gen.next_event()[0]["temp"] for _ in range(600)]
        return sum(temps) / len(temps)

    assert mean_temp(JULY) - mean_temp(JANUARY) == pytest.approx(2 * seasonal.TEMP_AMPLITUDE, abs=0.5)


def test_synthetic_humidity_stays_within_percent_range(stats, monkeypatch):
    monkeypatch.setattr(synthetic, "datetime", frozen(JANUARY))
    gen = synthetic.SyntheticGenerator(stats, anomaly_probability=0.0, anomaly_sigma_multiplier=4.0)
    assert all(0.0 <= gen.next_event()[0]["humidity"] <= 100.0 for _ in range(300))
