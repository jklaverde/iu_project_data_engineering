"""Seasonal curve for temp/humidity (D52, REQUIREMENTS.md §5.9 point 2).

The source dataset was collected in July, so July values are left unchanged
and mid-January is the extreme: temp drops by 2*A_t degrees, humidity rises
by 2*A_h points. A pure function of day-of-year - no state, no I/O.

Three identical copies, kept in sync by hand (separate images with separate
build contexts - same convention as environment.py's NUMERIC_METRICS):
backend/app/seasonal.py, producer/producer/seasonal.py,
spark_job/spark_job/seasonal.py. Change all three together.
"""

import math
import os
from datetime import datetime

TEMP_AMPLITUDE = float(os.getenv("HISTORY_SEASONAL_TEMP_AMPLITUDE", "8.0"))
HUMIDITY_AMPLITUDE = float(os.getenv("HISTORY_SEASONAL_HUMIDITY_AMPLITUDE", "7.5"))
# Day of year the source data represents (mid-July, 2020-07-12..20).
REFERENCE_DOY = float(os.getenv("HISTORY_SEASONAL_REFERENCE_DOY", "196"))

SEASONAL_METRICS = ("temp", "humidity")


def _term(dt: datetime) -> float:
    """0 at the reference day, -2 half a year away."""
    doy = dt.timetuple().tm_yday + (dt.hour + dt.minute / 60.0) / 24.0
    return math.cos(2.0 * math.pi * (doy - REFERENCE_DOY) / 365.25) - 1.0


def offset(metric: str, dt: datetime) -> float:
    """Additive seasonal shift for `metric` at `dt`; 0.0 for non-seasonal metrics."""
    if metric == "temp":
        return TEMP_AMPLITUDE * _term(dt)
    if metric == "humidity":
        return -HUMIDITY_AMPLITUDE * _term(dt)
    return 0.0


def apply(metric: str, value: float, dt: datetime) -> float:
    shifted = value + offset(metric, dt)
    if metric == "humidity":
        return min(max(shifted, 0.0), 100.0)
    return shifted
