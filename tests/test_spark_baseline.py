"""The Spark job seeds its anomaly EWMA at today's point on the seasonal curve (D52, FR-H3)."""

from datetime import datetime, timezone

import pytest

from spark_job import seasonal
from spark_job.baseline import seasonally_shifted

BASELINE = {"dev-a": {"temp": (22.0, 0.5), "humidity": (50.0, 2.0), "co": (0.005, 0.001)}}
JANUARY = datetime(2026, 1, 13, 12, tzinfo=timezone.utc)


def test_seed_means_move_with_the_season_and_stddevs_do_not():
    shifted = seasonally_shifted(BASELINE, JANUARY)["dev-a"]
    assert shifted["temp"] == pytest.approx((22.0 + seasonal.offset("temp", JANUARY), 0.5))
    assert shifted["humidity"] == pytest.approx((50.0 + seasonal.offset("humidity", JANUARY), 2.0))
    assert shifted["co"] == (0.005, 0.001)


def test_the_unshifted_baseline_is_left_intact():
    # device_thresholds persists the July baseline; only the seed is shifted.
    seasonally_shifted(BASELINE, JANUARY)
    assert BASELINE["dev-a"]["temp"] == (22.0, 0.5)
