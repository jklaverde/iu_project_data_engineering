"""Pure functions turning raw readings + Cassandra-persisted threshold stats
into role-appropriate environmental signals (R1 of the role-based redirect).
No I/O here - callers (routers/sensors.py) own reading from Cassandra.

Threshold data is NOT a separately-invented set of "safety limits" - it's the
exact same per-device/per-metric mean/stddev/ceiling that seeds Spark's own
streaming anomaly detector (spark_job/spark_job/anomaly_state.py,
spark_job/spark_job/baseline.py), persisted once at Spark startup into the
device_thresholds table (see docker-compose.yml / infra/cassandra/schema).
"critical" here mirrors Spark's own is_anomaly rule (|z| > sigma_n or a
ceiling crossing for co/lpg/smoke) by construction, so the planner map and
the admin's anomaly log agree for the same device/metric/moment.
"""

# Must match producer/producer/device_stats.py's NUMERIC_METRICS and
# spark_job/spark_job/baseline.py's CEILING_METRICS - kept in sync by hand
# since this is a separate service/container with its own dependency tree.
NUMERIC_METRICS = ("co", "humidity", "lpg", "smoke", "temp")
CEILING_METRICS = ("co", "smoke", "lpg")

WARNING_SIGMA = 2.0
CRITICAL_SIGMA = 3.0  # must match SPARK_JOB_ANOMALY_SIGMA_N's default

MIN_STDDEV = 1e-9


def metric_status(value: float, mean: float, stddev: float, ceiling: float | None) -> str:
    """"ok" | "warning" | "critical" for one metric reading."""
    if ceiling is not None and value > ceiling:
        return "critical"
    std = max(stddev, MIN_STDDEV)
    z = abs(value - mean) / std
    if z > CRITICAL_SIGMA:
        return "critical"
    if z > WARNING_SIGMA:
        return "warning"
    return "ok"


_STATUS_RANK = {"ok": 0, "warning": 1, "critical": 2}


def device_status(readings: dict, thresholds: dict) -> dict:
    """readings: {metric: value} for one device's latest reading.
    thresholds: {metric: {mean, stddev, ceiling}} for that device.

    Returns {"overall": "ok"|"warning"|"critical", "reason": str | None,
    "metrics": {metric: "ok"|"warning"|"critical"}}. "reason" names the
    worst-offending metric for a citizen-facing plain-language message
    (e.g. "elevated CO"), or None if everything is ok.
    """
    metrics: dict = {}
    worst_metric = None
    worst_rank = -1
    for metric in NUMERIC_METRICS:
        stats = thresholds.get(metric)
        value = readings.get(metric)
        if stats is None or value is None:
            continue
        ceiling = stats.get("ceiling") if metric in CEILING_METRICS else None
        status = metric_status(value, stats["mean"], stats["stddev"], ceiling)
        metrics[metric] = status
        if _STATUS_RANK[status] > worst_rank:
            worst_rank = _STATUS_RANK[status]
            worst_metric = metric

    overall = "ok" if worst_rank <= 0 else ("warning" if worst_rank == 1 else "critical")
    reason = None
    if overall != "ok" and worst_metric is not None:
        reason = f"{'elevated' if overall == 'warning' else 'critical'} {worst_metric}"
    return {"overall": overall, "reason": reason, "metrics": metrics}


def air_quality_score(readings: dict, thresholds: dict) -> float | None:
    """0 (worst) - 100 (best) - deliberately NOT the EPA AQI scale (where
    higher means worse); named "score" rather than "AQI" to avoid that
    mix-up. Worst-pollutant-dominates, same principle EPA AQI uses: each of
    co/lpg/smoke is normalized against its own device's ceiling, and the
    score reflects whichever pollutant is closest to (or over) its
    ceiling."""
    worst_fraction = None
    for metric in CEILING_METRICS:
        stats = thresholds.get(metric)
        value = readings.get(metric)
        if stats is None or value is None or not stats.get("ceiling"):
            continue
        fraction = value / stats["ceiling"]
        if worst_fraction is None or fraction > worst_fraction:
            worst_fraction = fraction
    if worst_fraction is None:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - worst_fraction)))


def comfort_index(temp: float | None, humidity: float | None) -> float | None:
    """Simple heat-index-style combination of temperature (C) and relative
    humidity (%): comfort drops as temperature rises above ~20C and as
    humidity moves away from a ~45% comfortable midpoint. 0-100, 100 = most
    comfortable. Illustrative, not a certified comfort standard."""
    if temp is None or humidity is None:
        return None
    temp_penalty = max(0.0, abs(temp - 21.0) - 2.0) * 4.0
    humidity_penalty = max(0.0, abs(humidity - 45.0) - 10.0) * 1.0
    return max(0.0, min(100.0, 100.0 - temp_penalty - humidity_penalty))


def chronic_exposure_ratio(agg_rows: list) -> float | None:
    """Fraction of aggregate windows (agg_1h rows, typically the last 24)
    where at least one anomaly was flagged - separates a persistent problem
    location from a one-off blip."""
    if not agg_rows:
        return None
    breached = sum(1 for r in agg_rows if (r.get("anomaly_count") or 0) > 0)
    return breached / len(agg_rows)


def trend_direction(recent_ratio: float | None, previous_ratio: float | None) -> str | None:
    """Compares two chronic_exposure_ratio values (e.g. this week vs. last
    week) -> "improving" | "worsening" | "stable" | None if either is
    missing."""
    if recent_ratio is None or previous_ratio is None:
        return None
    delta = recent_ratio - previous_ratio
    if delta > 0.05:
        return "worsening"
    if delta < -0.05:
        return "improving"
    return "stable"
