"""Planner-role signals with seasonal normal ranges (D52 FR-H4/FR-H5, D34/D35/D39)."""

from datetime import datetime, timedelta, timezone

import pytest

from app import environment as env
from app import seasonal

STATS = {"temp": {"mean": 22.0, "stddev": 0.5, "ceiling": None},
         "humidity": {"mean": 50.0, "stddev": 2.0, "ceiling": None},
         "co": {"mean": 0.005, "stddev": 0.001, "ceiling": 0.01}}
JULY = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)
JANUARY = datetime(2026, 1, 13, 12, tzinfo=timezone.utc)


# ------------------------------------------------------- seasonal ranges ---

def test_normal_band_moves_with_the_season():
    july_low, july_high = env.normal_band("temp", STATS["temp"], JULY)
    jan_low, jan_high = env.normal_band("temp", STATS["temp"], JANUARY)
    assert (july_low, july_high) == pytest.approx((21.0, 23.0), abs=0.01)  # noon, half a day past the reference
    assert jan_low == pytest.approx(21.0 - 2 * seasonal.TEMP_AMPLITUDE, abs=0.01)
    assert jan_high - jan_low == pytest.approx(july_high - july_low)


def test_non_seasonal_metrics_keep_a_fixed_band_floored_at_zero():
    assert env.normal_band("co", STATS["co"], JULY) == env.normal_band("co", STATS["co"], JANUARY)
    assert env.normal_band("co", {"mean": 0.001, "stddev": 0.001}, JULY)[0] == 0.0


def test_a_winter_reading_is_ok_in_winter_and_critical_in_summer():
    winter_reading = {"temp": 22.0 + seasonal.offset("temp", JANUARY)}
    assert env.device_status(winter_reading, STATS, JANUARY)["overall"] == "ok"
    july = env.device_status(winter_reading, STATS, JULY)
    assert july["overall"] == "critical" and july["reason"] == "critical temp"


def test_metric_ranges_report_the_band_in_force_at_the_reading_time():
    ranges = env.metric_ranges({"temp": 7.0, "co": 0.02}, STATS, JANUARY)
    low, high = env.normal_band("temp", STATS["temp"], JANUARY)
    assert ranges["temp"]["normal_min"] == pytest.approx(low)
    assert ranges["temp"]["normal_max"] == pytest.approx(high)
    assert ranges["co"]["status"] == "critical"  # over the ceiling regardless of season
    assert ranges["co"]["ceiling"] == 0.01


def test_status_defaults_to_now(monkeypatch):
    monkeypatch.setattr(env, "_now", lambda: JANUARY)
    assert env.device_status({"temp": 22.0 + seasonal.offset("temp", JANUARY)}, STATS)["overall"] == "ok"


# ------------------------------------------------- per-point timeline bands ---

def test_each_timeline_point_gets_the_band_of_its_own_period():
    points = [{"window_start": "2026-01-13T00:00:00.000Z"}, {"window_start": "2026-07-15T00:00:00.000Z"}]
    env.attach_normal_bands(points, "temp", STATS["temp"], "1d")
    assert points[0]["normal_max"] < points[1]["normal_min"]  # winter band entirely below summer band


def test_a_monthly_point_gets_the_widest_band_over_the_month():
    # October: the curve falls steeply, so the month spans more than one day's band.
    point = {"window_start": "2025-10-01T00:00:00.000Z"}
    env.attach_normal_bands([point], "temp", STATS["temp"], "1mo")
    start_low, start_high = env.normal_band("temp", STATS["temp"], datetime(2025, 10, 1, tzinfo=timezone.utc))
    end_low, end_high = env.normal_band("temp", STATS["temp"], datetime(2025, 11, 1, tzinfo=timezone.utc))
    assert point["normal_max"] == pytest.approx(start_high)
    assert point["normal_min"] == pytest.approx(end_low)


def test_points_are_left_alone_without_a_baseline():
    points = [{"window_start": "2026-01-13T00:00:00.000Z"}]
    env.attach_normal_bands(points, "temp", None, "1d")
    assert "normal_min" not in points[0]


# --------------------------------------------------------------- rollups ---

def _hour(ts, avg, count, anomalies=0):
    return {"window_start": ts, "temp_avg": avg, "temp_min": avg - 1, "temp_max": avg + 1,
            "event_count": count, "anomaly_count": anomalies}


def test_rollup_weights_by_event_count_and_returns_oldest_first():
    rows = [_hour("2026-09-02T10:00:00.000Z", 10.0, 1), _hour("2026-09-01T10:00:00.000Z", 20.0, 3),
            _hour("2026-09-01T11:00:00.000Z", 10.0, 1, anomalies=2)]
    points = env.rollup_metric_windows(rows, "temp", "1d")
    assert [p["window_start"] for p in points] == ["2026-09-01T00:00:00.000Z", "2026-09-02T00:00:00.000Z"]
    assert points[0]["avg"] == pytest.approx((20 * 3 + 10 * 1) / 4)
    assert points[0]["unhealthy"] and not points[1]["unhealthy"]


def test_weekly_rollup_keys_on_monday():
    points = env.rollup_metric_windows([_hour("2026-09-27T10:00:00.000Z", 1.0, 1)], "temp", "1w")  # a Sunday
    assert points[0]["window_start"] == "2026-09-21T00:00:00.000Z"


def test_dataset_rows_are_bucketed_by_their_derived_time_not_the_source_time():
    rows = [{"ts": "2026-01-13T10:05:00.000Z", "source_ts": "2020-07-15T10:05:00.000Z", "temp": 7.0},
            {"ts": "2026-01-13T10:45:00.000Z", "source_ts": "2020-07-15T10:45:00.000Z", "temp": 9.0}]
    points = env.bucket_dataset_rows(rows, "temp", "1h")
    assert points == [{"window_start": "2026-01-13T10:00:00.000Z", "avg": 8.0, "min": 7.0, "max": 9.0,
                       "anomaly_count": 0, "event_count": 2, "unhealthy": False}]


# ------------------------------------------------------ compare source ---

WINDOW_START = datetime(2025, 8, 1, tzinfo=timezone.utc)


def test_backfilled_history_covers_a_compare_window_before_the_deployment():
    history_start = WINDOW_START - timedelta(days=30)
    live_since = datetime(2026, 9, 27, tzinfo=timezone.utc)
    assert env.stored_history_covers(WINDOW_START, history_start, [live_since])


def test_without_a_backfill_only_live_history_counts():
    assert not env.stored_history_covers(WINDOW_START, None, [datetime(2026, 9, 27, tzinfo=timezone.utc)])
    assert env.stored_history_covers(WINDOW_START, None, [datetime(2025, 7, 1)])  # naive = UTC


def test_no_history_at_all_falls_back_to_the_dataset():
    assert not env.stored_history_covers(WINDOW_START, None, [])


# ------------------------------------------------------------ provenance ---

def test_replayed_readings_say_they_were_seasonally_adjusted():
    label = env.reading_provenance({"source_ts": "2020-07-12T10:00:00.000Z"})["label"]
    assert "originally collected 2020-07-12" in label and "seasonally adjusted" in label


def test_synthetic_readings_are_labeled_live():
    p = env.reading_provenance({"is_synthetic": True, "event_ts": "2026-09-27T11:00:00.000Z"})
    assert p["kind"] == "synthetic"
