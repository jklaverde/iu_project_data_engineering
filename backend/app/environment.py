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

from datetime import datetime, timedelta

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


METRIC_UNITS = {
    "co": "ppm-eq",
    "humidity": "%",
    "lpg": "ppm-eq",
    "smoke": "ppm-eq",
    "temp": "°C",
}


def metric_ranges(readings: dict, thresholds: dict) -> dict:
    """Per-metric {value, unit, normal_min, normal_max, ceiling, status} so
    the UI can render an actual-vs-acceptable gauge, not just a traffic-light
    dot. normal_min/max = mean +/- WARNING_SIGMA*stddev - the exact boundary
    metric_status() already uses for the ok/warning cutoff, so the gauge and
    the badge can never visually disagree."""
    out: dict = {}
    for metric in NUMERIC_METRICS:
        stats = thresholds.get(metric)
        value = readings.get(metric)
        if stats is None or value is None:
            continue
        ceiling = stats.get("ceiling") if metric in CEILING_METRICS else None
        spread = WARNING_SIGMA * max(stats["stddev"], MIN_STDDEV)
        normal_min = stats["mean"] - spread
        normal_max = stats["mean"] + spread
        out[metric] = {
            "value": value,
            "unit": METRIC_UNITS.get(metric, ""),
            "normal_min": max(0.0, normal_min) if metric != "temp" else normal_min,
            "normal_max": normal_max,
            "ceiling": ceiling,
            "status": metric_status(value, stats["mean"], stats["stddev"], ceiling),
        }
    return out


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


def metric_windows(rows: list, metric: str) -> list:
    """Projects one metric's avg/min/max out of agg_1m/agg_1h rows (as
    returned by CassandraReader.aggregates_sync) into the shape the
    planner role's timeline chart wants - one point per window, each
    flagged "unhealthy" when Spark counted any anomaly in that window.
    No rollup - used for the "1m"/"1h" granularities, which already have a
    Cassandra table at that exact resolution.

    Always returns oldest-first (ascending window_start) - aggregates_sync
    itself returns newest-first (it's built for "most recent N", not for
    charting), so this is where that gets normalized. rollup_metric_windows
    below shares this same contract; the timeline chart relies on both
    returning ascending order without needing to know which path produced
    the points."""
    out = []
    for r in rows:
        out.append({
            "window_start": r["window_start"],
            "avg": r.get(f"{metric}_avg"),
            "min": r.get(f"{metric}_min"),
            "max": r.get(f"{metric}_max"),
            "anomaly_count": r.get("anomaly_count") or 0,
            "event_count": r.get("event_count") or 0,
            "unhealthy": (r.get("anomaly_count") or 0) > 0,
        })
    out.sort(key=lambda p: p["window_start"] or "")
    return out


def _rollup_bucket_key(window_start_iso: str, granularity: str) -> str:
    """"1d" -> that calendar date; "1w" -> the Monday of that ISO week; "1mo"
    -> the 1st of that calendar month - all as plain date strings, used only
    as a grouping key (sorting them ascending already sorts chronologically
    for all three, since they're zero-padded ISO date strings)."""
    dt = datetime.fromisoformat(window_start_iso.replace("Z", "+00:00"))
    if granularity == "1d":
        return dt.date().isoformat()
    if granularity == "1mo":
        return dt.date().replace(day=1).isoformat()
    monday = dt.date() - timedelta(days=dt.weekday())
    return monday.isoformat()


def rollup_metric_windows(rows: list, metric: str, granularity: str) -> list:
    """Rolls agg_1h rows up into "1d", "1w", or "1mo" buckets - there is no
    dedicated Cassandra table at those coarser granularities (adding three
    more tables purely for a chart's display resolution isn't worth it;
    re-aggregating the existing hourly rows in Python is simpler and just
    as correct). avg is event-count-weighted so a bucket built from an
    uneven number of hourly windows isn't skewed toward the quieter ones.

    Returns oldest-first (ascending window_start), the same contract
    metric_windows() above guarantees - sorting the bucket keys already
    gives ascending order here since they're ISO date strings, but this is
    stated explicitly because a caller (or a future edit to this function)
    should never have to guess which of the two functions needs a reverse
    and which doesn't."""
    buckets: dict = {}
    for r in rows:
        if not r.get("window_start"):
            continue
        key = _rollup_bucket_key(r["window_start"], granularity)
        b = buckets.setdefault(key, {
            "weighted_sum": 0.0, "weight": 0, "min": None, "max": None,
            "anomaly_count": 0, "event_count": 0,
        })
        events = r.get("event_count") or 0
        avg = r.get(f"{metric}_avg")
        if avg is not None:
            weight = max(events, 1)
            b["weighted_sum"] += avg * weight
            b["weight"] += weight
        mn, mx = r.get(f"{metric}_min"), r.get(f"{metric}_max")
        if mn is not None:
            b["min"] = mn if b["min"] is None else min(b["min"], mn)
        if mx is not None:
            b["max"] = mx if b["max"] is None else max(b["max"], mx)
        b["anomaly_count"] += r.get("anomaly_count") or 0
        b["event_count"] += events

    out = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        out.append({
            "window_start": f"{key}T00:00:00.000Z",
            "avg": (b["weighted_sum"] / b["weight"]) if b["weight"] else None,
            "min": b["min"],
            "max": b["max"],
            "anomaly_count": b["anomaly_count"],
            "event_count": b["event_count"],
            "unhealthy": b["anomaly_count"] > 0,
        })
    return out
