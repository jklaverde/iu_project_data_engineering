"""Dataset Explorer reader on the derived file (D38, D52, FR-P2/FR-H1)."""

import os
from datetime import datetime, timezone

import pytest

from app import history_backfill as hb
from app.dataset_reader import DatasetReader
from conftest import SOURCE_DEVICES

ANCHOR = datetime(2026, 9, 27, 11, tzinfo=timezone.utc)


def build_derived(source_csv, path, span_days=10, seed=51):
    settings = hb.Settings("c", 9042, "iot", str(source_csv), str(path), span_days, 60, seed, 3.0, 1.5, 1)
    devices, origin = hb.load_source(settings.source_csv, 1.5)
    hb.derive(settings, devices, origin, ANCHOR)
    return path


@pytest.fixture
def derived_csv(source_csv, tmp_path):
    return build_derived(source_csv, tmp_path / "iot_telemetry_derived.csv")


def test_missing_file_reads_as_not_available(tmp_path):
    reader = DatasetReader(str(tmp_path / "not-there.csv"))
    assert reader.summary() == {"available": False, "devices": []}
    assert reader.query(None, None, None, 10) == []


def test_summary_lists_each_device_with_its_derived_range(derived_csv):
    summary = DatasetReader(str(derived_csv)).summary()
    assert summary["available"] is True
    assert sorted(d["device_id"] for d in summary["devices"]) == sorted(SOURCE_DEVICES)
    dev = summary["devices"][0]
    assert dev["row_count"] == 10 * 24
    assert dev["min_ts"] == "2026-09-17T11:00:00.000Z"
    assert dev["max_ts"] == "2026-09-27T10:00:00.000Z"


def test_query_filters_by_device_and_time_window(derived_csv):
    reader = DatasetReader(str(derived_csv))
    rows = reader.query("dev-b",
                        datetime(2026, 9, 20, 0, tzinfo=timezone.utc),
                        datetime(2026, 9, 20, 5, tzinfo=timezone.utc), 100)
    assert [r["ts"] for r in rows] == [f"2026-09-20T0{h}:00:00.000Z" for h in range(6)]
    assert {r["device_id"] for r in rows} == {"dev-b"}


def test_each_reading_carries_its_original_source_time(derived_csv):
    row = DatasetReader(str(derived_csv)).query("dev-a", None, None, 1)[0]
    assert row["source_ts"].startswith("2020-07-")
    assert set(row) == {"ts", "source_ts", "device_id", "co", "humidity", "lpg", "smoke", "temp", "light", "motion"}
    assert isinstance(row["light"], bool)


def test_query_respects_the_limit(derived_csv):
    assert len(DatasetReader(str(derived_csv)).query(None, None, None, 7)) == 7


def test_reader_reloads_when_the_file_is_replaced(source_csv, derived_csv, tmp_path):
    reader = DatasetReader(str(derived_csv))
    assert reader.summary()["devices"][0]["row_count"] == 10 * 24

    replacement = build_derived(source_csv, tmp_path / "longer.csv", span_days=12)
    os.replace(replacement, derived_csv)
    stat = os.stat(derived_csv)
    os.utime(derived_csv, (stat.st_atime, stat.st_mtime + 5))  # guarantee a new mtime

    assert reader.summary()["devices"][0]["row_count"] == 12 * 24
