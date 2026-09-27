"""history-backfill Job (D52, REQUIREMENTS.md §5.9, FR-H1/FR-H2).

Covers the derivation (looping, time of day, sampling, seasonal shift,
determinism), the anomaly rule, the agg_1h write path, and the Job's
idempotency workflow through main() against a fake Cassandra session.
"""

import csv
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import history_backfill as hb
from app import seasonal
from conftest import SOURCE_DEVICES

ANCHOR = datetime(2026, 9, 27, 11, 0, tzinfo=timezone.utc)
SPAN_DAYS = 20
SAMPLE_MINUTES = 60


def make_settings(source_csv, derived_csv, **overrides):
    values = dict(
        cassandra_host="cassandra", cassandra_port=9042, keyspace="iot",
        source_csv=str(source_csv), derived_csv=str(derived_csv),
        span_days=SPAN_DAYS, sample_minutes=SAMPLE_MINUTES, seed=51,
        sigma_n=3.0, ceiling_multiplier=1.5, wait_seconds=1,
    )
    values.update(overrides)
    return hb.Settings(**values)


def read_derived(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def derived(source_csv, tmp_path):
    settings = make_settings(source_csv, tmp_path / "derived.csv")
    devices, origin = hb.load_source(settings.source_csv, settings.ceiling_multiplier)
    hours, rows = hb.derive(settings, devices, origin, ANCHOR)
    return SimpleNamespace(settings=settings, devices=devices, origin=origin, hours=hours, rows=rows,
                           csv_rows=read_derived(settings.derived_csv))


# ---------------------------------------------------------------- source ---

def test_load_source_groups_by_device_and_computes_the_spark_baseline(source_csv):
    devices, origin = hb.load_source(str(source_csv), 1.5)
    assert sorted(devices) == sorted(SOURCE_DEVICES)
    assert origin == datetime(2020, 7, 12, tzinfo=timezone.utc).timestamp()  # UTC midnight
    src = devices["dev-a"]
    assert src.ts == sorted(src.ts)
    temps = [r[4] for r in src.rows]
    assert src.mean["temp"] == pytest.approx(sum(temps) / len(temps))
    assert src.std["temp"] > 0
    # ceiling = max(max, p99.9) * multiplier, gas/smoke metrics only
    assert src.ceiling["co"] == pytest.approx(max(r[0] for r in src.rows) * 1.5)
    assert "temp" not in src.ceiling


# ------------------------------------------------------------ derivation ---

def test_derived_file_covers_the_span_at_the_sampling_interval(derived):
    expected_per_device = SPAN_DAYS * 24 * 60 // SAMPLE_MINUTES
    assert derived.rows == expected_per_device * len(SOURCE_DEVICES) == len(derived.csv_rows)
    ts = [int(r["ts"]) for r in derived.csv_rows]
    assert min(ts) == int((ANCHOR - timedelta(days=SPAN_DAYS)).timestamp())
    assert max(ts) == int(ANCHOR.timestamp()) - SAMPLE_MINUTES * 60  # [start, anchor)
    assert ts == sorted(ts)  # globally ordered, as DatasetReader assumes


def test_derived_readings_keep_their_time_of_day(derived):
    # Looping (not stretching) the 8-day cycle: each derived reading comes
    # from a source reading at the same UTC time of day.
    for r in derived.csv_rows[:: 97]:
        at = datetime.fromtimestamp(int(r["ts"]), tz=timezone.utc)
        src = datetime.fromtimestamp(float(r["source_ts"]), tz=timezone.utc)
        drift = abs((at.hour * 60 + at.minute) - (src.hour * 60 + src.minute))
        assert min(drift, 1440 - drift) <= 5


def test_derived_readings_cycle_through_all_eight_source_days(derived):
    source_days = {datetime.fromtimestamp(float(r["source_ts"]), tz=timezone.utc).date() for r in derived.csv_rows}
    assert len(source_days) == 8


def test_temperature_follows_the_seasonal_curve(source_csv, tmp_path):
    # A full year, so both ends of the curve are present.
    settings = make_settings(source_csv, tmp_path / "year.csv", span_days=366, sample_minutes=240)
    devices, origin = hb.load_source(settings.source_csv, 1.5)
    hb.derive(settings, devices, origin, ANCHOR)
    rows = [r for r in read_derived(settings.derived_csv) if r["device"] == "dev-a"]

    def monthly_mean(month):
        vals = [float(r["temp"]) for r in rows
                if datetime.fromtimestamp(int(r["ts"]), tz=timezone.utc).month == month]
        return sum(vals) / len(vals)

    difference = monthly_mean(7) - monthly_mean(1)
    # January averages close to 2*A_t colder than July (the curve is not at
    # its extreme for the whole month, hence the tolerance).
    assert difference == pytest.approx(2 * seasonal.TEMP_AMPLITUDE, rel=0.1)


def test_derivation_is_deterministic_for_the_same_anchor_and_seed(source_csv, tmp_path):
    outputs = []
    for name in ("one.csv", "two.csv"):
        settings = make_settings(source_csv, tmp_path / name)
        devices, origin = hb.load_source(settings.source_csv, 1.5)
        hb.derive(settings, devices, origin, ANCHOR)
        outputs.append((tmp_path / name).read_bytes())
    assert outputs[0] == outputs[1]


def test_a_different_seed_changes_the_noise(source_csv, tmp_path):
    a = make_settings(source_csv, tmp_path / "a.csv", seed=1)
    b = make_settings(source_csv, tmp_path / "b.csv", seed=2)
    for s in (a, b):
        devices, origin = hb.load_source(s.source_csv, 1.5)
        hb.derive(s, devices, origin, ANCHOR)
    assert (tmp_path / "a.csv").read_bytes() != (tmp_path / "b.csv").read_bytes()


def test_derive_leaves_no_temporary_file_behind(derived):
    # written to <path>.tmp and renamed into place, so a reader never sees a half-written file
    import os
    assert os.path.exists(derived.settings.derived_csv)
    assert not os.path.exists(derived.settings.derived_csv + ".tmp")


def test_hourly_aggregates_match_the_derived_rows(derived):
    per_hour = SAMPLE_MINUTES // 60 or 1
    assert len(derived.hours) == SPAN_DAYS * 24 * len(SOURCE_DEVICES)
    agg = next(iter(derived.hours.values()))
    assert agg.count == per_hour
    for m in hb.AGG_METRICS:
        assert agg.mins[m] <= agg.sums[m] / agg.count <= agg.maxs[m]


# ---------------------------------------------------------- anomaly rule ---

def _baseline():
    return hb.DeviceSource(
        ts=[], rows=[],
        mean={"co": 0.005, "humidity": 50.0, "lpg": 0.008, "smoke": 0.02, "temp": 22.0},
        std={"co": 0.001, "humidity": 2.0, "lpg": 0.001, "smoke": 0.002, "temp": 0.5},
        ceiling={"co": 0.01, "lpg": 0.012, "smoke": 0.03},
    )


def _values(at, **overrides):
    src = _baseline()
    values = {m: src.mean[m] + seasonal.offset(m, at) for m in hb.NUMERIC_METRICS}
    values.update(overrides)
    return values


JULY = datetime(2025, 7, 15, tzinfo=timezone.utc)
JANUARY = datetime(2026, 1, 13, tzinfo=timezone.utc)


def test_a_reading_on_the_seasonal_mean_is_not_an_anomaly():
    assert not hb._is_anomaly(_values(JANUARY), _baseline(), JANUARY, 3.0)
    assert not hb._is_anomaly(_values(JULY), _baseline(), JULY, 3.0)


def test_a_normal_winter_reading_is_only_normal_in_winter():
    winter = _values(JANUARY)
    assert not hb._is_anomaly(winter, _baseline(), JANUARY, 3.0)
    assert hb._is_anomaly(winter, _baseline(), JULY, 3.0)  # same values judged in July


def test_sigma_rule_flags_a_deviation():
    assert hb._is_anomaly(_values(JULY, humidity=50.0 + 7.0), _baseline(), JULY, 3.0)


def test_ceiling_rule_flags_gas_over_the_ceiling():
    assert hb._is_anomaly(_values(JULY, co=0.02), _baseline(), JULY, 100.0)


# ------------------------------------------------------------ Cassandra ---

class FakeSession:
    """Just enough of cassandra.cluster.Session for history_backfill."""

    def __init__(self, meta=None, existing_hours=()):
        self.meta = meta
        self.existing_hours = set(existing_hours)  # {(device_id, window_start datetime)}
        self.statements = []

    def prepare(self, query):
        return SimpleNamespace(query=query)

    def execute(self, query, params=None):
        text = getattr(query, "query", query)
        self.statements.append((text, params))
        if text.startswith("SELECT anchor_ts"):
            return SimpleNamespace(one=lambda: self.meta)
        if text.startswith("INSERT INTO history_backfill"):
            _, anchor, _start, span, sample, seed = params
            self.meta = SimpleNamespace(anchor_ts=anchor, span_days=span, sample_minutes=sample,
                                        seed=seed, completed_at=None)
            return None
        if text.startswith("UPDATE history_backfill"):
            self.meta.completed_at = params[1]
            return None
        if text.startswith("SELECT window_start FROM agg_1h"):
            device_id, month, since = params
            return [SimpleNamespace(window_start=ws) for d, ws in self.existing_hours
                    if d == device_id and (ws.year, ws.month) == (month.year, month.month) and ws >= since]
        raise AssertionError(f"unexpected statement: {text}")

    def count(self, prefix):
        return sum(1 for text, _ in self.statements if text.startswith(prefix))


class FakeConcurrent:
    """Stands in for cassandra.concurrent.execute_concurrent_with_args."""

    def __init__(self):
        self.calls = []

    def __call__(self, session, stmt, params, **kwargs):
        params = list(params)
        self.calls.append((params, kwargs))
        return iter([(True, None)] * len(params))

    @property
    def rows(self):
        return [p for params, _ in self.calls for p in params]


def test_write_agg_1h_skips_existing_hours_and_writes_in_chunks(derived, monkeypatch):
    fake = FakeConcurrent()
    monkeypatch.setattr(hb, "execute_concurrent_with_args", fake)
    monkeypatch.setattr(hb, "WRITE_CHUNK", 100)
    skip = set(list(derived.hours)[:5])

    written = hb.write_agg_1h(FakeSession(), derived.hours, skip)

    assert written == len(derived.hours) - 5
    assert all(len(params) <= 100 for params, _ in fake.calls)
    assert all(kwargs.get("results_generator") for _, kwargs in fake.calls)
    written_keys = {(r[0], int(r[2].timestamp())) for r in fake.rows}
    assert written_keys.isdisjoint(skip)
    row = fake.rows[0]
    assert row[1] == row[2].date().replace(day=1)          # month partition
    assert row[3] - row[2] == timedelta(hours=1)          # window_end
    assert len(row) == 28                                 # every agg_1h column


def test_existing_live_hours_reads_every_month_of_the_span():
    live = datetime(2026, 9, 27, 11, tzinfo=timezone.utc)
    session = FakeSession(existing_hours=[("dev-a", live)])
    since = ANCHOR - timedelta(days=65)
    found = hb.existing_live_hours(session, ["dev-a", "dev-b"], since, ANCHOR)
    assert found == {("dev-a", int(live.timestamp()))}
    assert session.count("SELECT window_start FROM agg_1h") == 2 * 3  # 2 devices x Jul/Aug/Sep


# ------------------------------------------------------ main() workflows ---

@pytest.fixture
def job(source_csv, tmp_path, monkeypatch):
    """Runs main() against a FakeSession; returns a helper namespace."""
    derived_csv = tmp_path / "iot_telemetry_derived.csv"
    for key, value in {
        "CASSANDRA_HOST": "cassandra", "CASSANDRA_PORT": "9042", "CASSANDRA_KEYSPACE": "iot",
        "HISTORY_SOURCE_CSV_PATH": str(source_csv), "HISTORY_DERIVED_CSV_PATH": str(derived_csv),
        "HISTORY_SPAN_DAYS": str(SPAN_DAYS), "HISTORY_SAMPLE_MINUTES": str(SAMPLE_MINUTES), "HISTORY_SEED": "51",
    }.items():
        monkeypatch.setenv(key, value)
    fake = FakeConcurrent()
    monkeypatch.setattr(hb, "execute_concurrent_with_args", fake)
    state = SimpleNamespace(session=FakeSession(), concurrent=fake, derived_csv=derived_csv)
    monkeypatch.setattr(hb, "wait_for", lambda settings: (SimpleNamespace(shutdown=lambda: None), state.session))
    state.run = hb.main
    return state


def test_fresh_run_records_anchor_writes_everything_and_completes(job):
    job.run()
    meta = job.session.meta
    assert meta.completed_at is not None
    assert meta.anchor_ts.minute == meta.anchor_ts.second == 0  # truncated to the hour
    assert len(job.concurrent.rows) == SPAN_DAYS * 24 * len(SOURCE_DEVICES)
    assert job.derived_csv.exists()
    sidecar = json.loads(job.derived_csv.with_name(job.derived_csv.name + ".json").read_text())
    assert sidecar["anchor_ts"] == meta.anchor_ts.isoformat()
    # The anchor row is recorded before the agg_1h writes (which read existing
    # hours first) and marked complete only after them, so a crash can resume.
    texts = [t for t, _ in job.session.statements]
    record = texts.index(next(t for t in texts if t.startswith("INSERT INTO history_backfill")))
    existing_check = texts.index(next(t for t in texts if t.startswith("SELECT window_start FROM agg_1h")))
    complete = texts.index(next(t for t in texts if t.startswith("UPDATE history_backfill")))
    assert record < existing_check < complete


def test_rerun_after_completion_changes_nothing(job):
    job.run()
    rows_after_first = len(job.concurrent.rows)
    before = job.derived_csv.read_bytes()
    job.run()
    assert len(job.concurrent.rows) == rows_after_first
    assert job.derived_csv.read_bytes() == before
    assert job.session.count("INSERT INTO history_backfill") == 1


def test_completed_run_only_regenerates_a_missing_derived_file(job):
    job.run()
    before = job.derived_csv.read_bytes()
    rows_after_first = len(job.concurrent.rows)
    job.derived_csv.unlink()

    job.run()

    assert job.derived_csv.read_bytes() == before        # same anchor + seed => same file
    assert len(job.concurrent.rows) == rows_after_first  # no Cassandra writes


def test_incomplete_run_resumes_with_the_recorded_anchor(job):
    recorded = datetime(2026, 9, 20, 5, tzinfo=timezone.utc)
    job.session.meta = SimpleNamespace(anchor_ts=recorded.replace(tzinfo=None), span_days=SPAN_DAYS,
                                       sample_minutes=SAMPLE_MINUTES, seed=51, completed_at=None)
    job.run()
    starts = [r[2] for r in job.concurrent.rows]
    assert max(starts) == recorded - timedelta(hours=1)
    assert job.session.meta.completed_at is not None


def test_retry_does_not_rewrite_hours_already_present(job):
    # The live OOM case: a first attempt wrote some hours and died.
    recorded = ANCHOR
    already = [(d, recorded - timedelta(hours=h)) for d in SOURCE_DEVICES for h in range(1, 11)]
    job.session.meta = SimpleNamespace(anchor_ts=recorded, span_days=SPAN_DAYS,
                                       sample_minutes=SAMPLE_MINUTES, seed=51, completed_at=None)
    job.session.existing_hours = set(already)
    job.run()
    written = {(r[0], r[2]) for r in job.concurrent.rows}
    assert written.isdisjoint(already)
    assert len(written) == SPAN_DAYS * 24 * len(SOURCE_DEVICES) - len(already)


def test_recorded_settings_win_over_changed_configuration(job, monkeypatch):
    job.session.meta = SimpleNamespace(anchor_ts=ANCHOR, span_days=10, sample_minutes=SAMPLE_MINUTES,
                                       seed=51, completed_at=None)
    job.run()  # environment still says SPAN_DAYS=20
    assert len(job.concurrent.rows) == 10 * 24 * len(SOURCE_DEVICES)
