"""The seasonal curve (D52, REQUIREMENTS.md §5.9 point 2)."""

from datetime import datetime, timezone

import pytest

from app import seasonal

JULY_REFERENCE = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)   # day of year 196
MID_JANUARY = datetime(2026, 1, 13, 12, 0, tzinfo=timezone.utc)      # ~half a year away


def test_the_three_copies_are_identical():
    # backend, producer and spark_job each ship their own copy (separate
    # images); a drift between them would put live data, the anomaly seed
    # and the normal ranges on different curves.
    from conftest import ROOT
    copies = [
        (ROOT / p).read_bytes().replace(b"\r\n", b"\n")
        for p in ("backend/app/seasonal.py", "producer/producer/seasonal.py", "spark_job/spark_job/seasonal.py")
    ]
    assert copies[0] == copies[1] == copies[2]


def test_reference_day_is_unchanged():
    assert seasonal.offset("temp", JULY_REFERENCE) == pytest.approx(0.0, abs=1e-9)
    assert seasonal.offset("humidity", JULY_REFERENCE) == pytest.approx(0.0, abs=1e-9)


def test_mid_january_is_the_extreme():
    assert seasonal.offset("temp", MID_JANUARY) == pytest.approx(-2 * seasonal.TEMP_AMPLITUDE, abs=0.01)
    assert seasonal.offset("humidity", MID_JANUARY) == pytest.approx(2 * seasonal.HUMIDITY_AMPLITUDE, abs=0.01)


def test_curve_is_monotonic_from_july_to_january():
    months = [datetime(2025, m, 15, tzinfo=timezone.utc) for m in (7, 8, 9, 10, 11, 12)]
    offsets = [seasonal.offset("temp", d) for d in months]
    assert offsets == sorted(offsets, reverse=True)


@pytest.mark.parametrize("metric", ["co", "lpg", "smoke", "pressure", "light"])
def test_other_metrics_are_not_shifted(metric):
    assert seasonal.offset(metric, MID_JANUARY) == 0.0
    assert seasonal.apply(metric, 1.23, MID_JANUARY) == 1.23


def test_humidity_is_clamped_to_percent_range():
    assert seasonal.apply("humidity", 99.0, MID_JANUARY) == 100.0
    assert seasonal.apply("humidity", -5.0, JULY_REFERENCE) == 0.0


def test_temp_is_not_clamped():
    assert seasonal.apply("temp", 1.0, MID_JANUARY) == pytest.approx(1.0 - 2 * seasonal.TEMP_AMPLITUDE, abs=0.01)
