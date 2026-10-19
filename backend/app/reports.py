"""Environmental officer reports (D55, UC-15-UC-18, FR-O1-O10).

Pure functions over agg_1h rows (as returned by CassandraReader), the same
shape environment.py works on. No I/O here - routers/reports.py reads
Cassandra and calls these; report_xlsx.py turns the results into workbooks.

One definition of "out of range" (FR-O2) is used everywhere: an hour in which
Spark flagged at least one anomaly AND the hour's min or max lies outside the
normal range in force during that hour, or its max is above the ceiling. That
is exactly the test the planner's out-of-range log (BoundaryLog.tsx) applies
at hourly resolution, including the widest-band-over-the-period rule of
environment.attach_normal_bands, so a report and the log never disagree.

Reports work in local time (Europe/Berlin): a municipality's "September" and
"22:00-06:00" are local. The EU daylight-saving rule is computed here rather
than read from zoneinfo, because tz data is not guaranteed in every runtime
this code and its tests run in (it is missing on a plain Windows Python).
"""

from datetime import date, datetime, timedelta, timezone

from . import environment

METRICS = environment.NUMERIC_METRICS  # pressure is simulated - never reported (FR-O9)
POLLUTANTS = environment.CEILING_METRICS

METRIC_LABELS = {
    "co": "CO",
    "lpg": "LPG",
    "smoke": "Smoke",
    "temp": "Temperature",
    "humidity": "Humidity",
}

# FR-O9: every report carries its own caveats - a printed page travels
# without the app around it. User-facing text: no internal codes.
CAVEATS = (
    "Normal ranges are statistical baselines from each sensor's own history, not legal limit values.",
    "Each location is judged against its own normal range, so a ranking shows which location departed most "
    "often from its own usual behaviour - not which one has the most pollution. Compare the averages for that.",
    "An hour counts as out of range when the pipeline flagged an unusual reading in it and the hour's "
    "lowest or highest value lies outside the normal range in force at that time (temperature and "
    "humidity ranges follow the season), or its highest value is above the safety limit.",
    "History from before the system went live is derived from a 2020 source dataset (its 8 days "
    "repeated, temperature and humidity adjusted for the season). It is illustrative, not measured.",
    "Three sensors are point measurements at their own locations, not coverage of the whole city.",
    "Atmospheric pressure is simulated and is not part of any report.",
)

MAX_INQUIRY_DAYS = 92
MAX_EXTRACT_DAYS = 366
FACT_SHEET_DAYS = 30
HEATMAP_MONTHS = 12
TOP_EPISODES = 5

# Character label for pollutants (FR-O5): coefficient of variation of the
# hourly averages over the fact sheet's 30 days. Calibrated against the
# derived history (see D55): the residential sensor sits well under the
# first cutoff, the river-side one well over the second.
STEADY_MAX_CV = 0.15
VARIABLE_MAX_CV = 0.30

_HOUR = timedelta(hours=1)


# ------------------------------------------------------------ local time ---

def _last_sunday(year: int, month: int) -> date:
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def berlin_offset(utc: datetime) -> timedelta:
    """+2h between 01:00 UTC on the last Sunday of March and 01:00 UTC on the
    last Sunday of October (EU rule), +1h otherwise."""
    utc = utc.astimezone(timezone.utc)
    start = datetime.combine(_last_sunday(utc.year, 3), datetime.min.time(), timezone.utc) + _HOUR
    end = datetime.combine(_last_sunday(utc.year, 10), datetime.min.time(), timezone.utc) + _HOUR
    return timedelta(hours=2) if start <= utc < end else timedelta(hours=1)


def to_local(utc: datetime) -> datetime:
    """Naive Europe/Berlin wall-clock time for an aware UTC instant."""
    return (utc.astimezone(timezone.utc) + berlin_offset(utc)).replace(tzinfo=None)


def local_midnight_utc(day: date) -> datetime:
    """The UTC instant at which local `day` begins. Midnight is never inside a
    DST transition (those happen at 02:00/03:00 local), so the offset at
    midnight-minus-a-guess is the right one."""
    guess = datetime.combine(day, datetime.min.time(), timezone.utc) - timedelta(hours=1)
    return datetime.combine(day, datetime.min.time(), timezone.utc) - berlin_offset(guess)


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, end) of a local calendar month, as UTC instants."""
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return local_midnight_utc(date(year, month, 1)), local_midnight_utc(nxt)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _local_iso(dt: datetime) -> str:
    return to_local(dt).isoformat(timespec="minutes")


# --------------------------------------------------------- hour judgement ---

def _start(row: dict) -> datetime | None:
    return environment.parse_iso(row.get("window_start"))


def hour_band(metric: str, stats: dict, start: datetime) -> tuple[float, float]:
    """The widest normal band in force during the hour - the same three-sample
    rule environment.attach_normal_bands uses for a 1h timeline point."""
    bands = [environment.normal_band(metric, stats, start + k * _HOUR / 2) for k in (0, 1, 2)]
    return min(b[0] for b in bands), max(b[1] for b in bands)


def judge_hour(row: dict, metric: str, stats: dict | None) -> dict:
    """{"out_of_range": bool, "over_limit": bool} for one agg_1h row (FR-O2)."""
    verdict = {"out_of_range": False, "over_limit": False}
    start = _start(row)
    if not stats or start is None or (row.get("anomaly_count") or 0) <= 0:
        return verdict
    mn, mx = row.get(f"{metric}_min"), row.get(f"{metric}_max")
    if mn is None and mx is None:
        return verdict
    low, high = hour_band(metric, stats, start)
    ceiling = stats.get("ceiling") if metric in POLLUTANTS else None
    over = ceiling is not None and mx is not None and mx > ceiling
    verdict["over_limit"] = over
    verdict["out_of_range"] = over or (mx is not None and mx > high) or (mn is not None and mn < low)
    return verdict


# -------------------------------------------------------------- summaries ---

def _in_period(rows: list, start: datetime, end: datetime) -> list:
    return [r for r in rows if (s := _start(r)) is not None and start <= s < end]


def metric_summary(rows: list, metric: str, stats: dict | None) -> dict:
    """Hours with data, out-of-range and over-limit hours, the event-weighted
    average and the peak (highest hourly max, with its local time)."""
    hours = oor = over = 0
    weighted = weight = 0.0
    peak = peak_at = None
    for r in rows:
        avg = r.get(f"{metric}_avg")
        if avg is None:
            continue
        hours += 1
        w = max(r.get("event_count") or 0, 1)
        weighted += avg * w
        weight += w
        mx = r.get(f"{metric}_max")
        if mx is not None and (peak is None or mx > peak):
            peak, peak_at = mx, _start(r)
        verdict = judge_hour(r, metric, stats)
        oor += verdict["out_of_range"]
        over += verdict["over_limit"]
    return {
        "hours_with_data": hours,
        "out_of_range_hours": oor,
        "over_limit_hours": over,
        "out_of_range_share": (oor / hours) if hours else None,
        "average": (weighted / weight) if weight else None,
        "peak": peak,
        "peak_at": _local_iso(peak_at) if peak_at else None,
    }


def out_of_range_hours(rows: list, thresholds: dict) -> list:
    """Every (row, metric, verdict) that is out of range, oldest first."""
    out = []
    for r in sorted(rows, key=lambda r: r.get("window_start") or ""):
        for metric in METRICS:
            verdict = judge_hour(r, metric, thresholds.get(metric))
            if verdict["out_of_range"]:
                out.append((r, metric, verdict))
    return out


def episodes(rows: list, device_id: str, thresholds: dict) -> list:
    """Consecutive out-of-range hours of one location and metric, merged."""
    found = []
    open_by_metric: dict = {}
    for r, metric, verdict in out_of_range_hours(rows, thresholds):
        start = _start(r)
        mx = r.get(f"{metric}_max")
        ep = open_by_metric.get(metric)
        if ep is not None and ep["_end"] == start:
            ep["_end"] = start + _HOUR
            ep["hours"] += 1
            ep["over_limit"] = ep["over_limit"] or verdict["over_limit"]
            if mx is not None and (ep["peak"] is None or mx > ep["peak"]):
                ep["peak"], ep["_peak_at"] = mx, start
            continue
        ep = {
            "device_id": device_id, "metric": metric, "_start": start, "_end": start + _HOUR,
            "hours": 1, "peak": mx, "_peak_at": start, "over_limit": verdict["over_limit"],
        }
        open_by_metric[metric] = ep
        found.append(ep)
    out = []
    for ep in found:
        out.append({
            "device_id": ep["device_id"], "metric": ep["metric"],
            "start": _local_iso(ep["_start"]), "end": _local_iso(ep["_end"]),
            "hours": ep["hours"], "peak": ep["peak"],
            "peak_at": _local_iso(ep["_peak_at"]), "over_limit": ep["over_limit"],
        })
    return out


def hours_any_out_of_range(rows: list, thresholds: dict) -> int:
    """Distinct hours in which at least one metric was out of range."""
    return len({r.get("window_start") for r, _, _ in out_of_range_hours(rows, thresholds)})


def _change(current: int, previous: int, previous_hours: int) -> int | None:
    return (current - previous) if previous_hours else None


# --------------------------------------------------------- monthly report ---

def monthly_report(year: int, month: int, rows_by_device: dict, metadata: list, thresholds: dict) -> dict:
    """UC-15 / FR-O3. rows_by_device: {device_id: agg_1h rows} covering at
    least the month, the previous month and the same month a year earlier."""
    periods = {
        "current": (year, month),
        "previous": shift_month(year, month, -1),
        "year_ago": shift_month(year, month, -12),
    }
    bounds = {k: month_bounds(*ym) for k, ym in periods.items()}

    locations, ranking, all_episodes = [], [], []
    for meta in metadata:
        device_id = meta["device_id"]
        device_thresholds = thresholds.get(device_id, {})
        rows = rows_by_device.get(device_id, [])
        by_period = {k: _in_period(rows, *b) for k, b in bounds.items()}

        metrics = {}
        for metric in METRICS:
            stats = device_thresholds.get(metric)
            metrics[metric] = {k: metric_summary(by_period[k], metric, stats) for k in periods}

        totals = {k: hours_any_out_of_range(by_period[k], device_thresholds) for k in periods}
        data_hours = {k: len(by_period[k]) for k in periods}
        over = sum(metrics[m]["current"]["over_limit_hours"] for m in POLLUTANTS)
        locations.append({**_location(meta), "metrics": metrics})
        ranking.append({
            **_location(meta),
            "hours_with_data": data_hours["current"],
            "out_of_range_hours": totals["current"],
            "over_limit_hours": over,
            "change_vs_previous": _change(totals["current"], totals["previous"], data_hours["previous"]),
            "change_vs_year_ago": _change(totals["current"], totals["year_ago"], data_hours["year_ago"]),
        })
        all_episodes += [{**e, "name": meta["name"]} for e in episodes(by_period["current"], device_id, device_thresholds)]

    ranking.sort(key=lambda r: (-r["out_of_range_hours"], -r["over_limit_hours"], r["name"]))
    order = [r["device_id"] for r in ranking]
    locations.sort(key=lambda loc: order.index(loc["device_id"]))  # detail sections follow the ranking
    all_episodes.sort(key=lambda e: (-e["hours"], not e["over_limit"], e["start"]))
    return {
        "month": f"{year:04d}-{month:02d}",
        "previous_month": "%04d-%02d" % periods["previous"],
        "year_ago_month": "%04d-%02d" % periods["year_ago"],
        "period": {"start": iso_utc(bounds["current"][0]), "end": iso_utc(bounds["current"][1])},
        "locations": locations,
        "ranking": ranking,
        "episodes": all_episodes[:TOP_EPISODES],
        "units": dict(environment.METRIC_UNITS),
        "labels": dict(METRIC_LABELS),
        "caveats": list(CAVEATS),
    }


def _location(meta: dict) -> dict:
    return {"device_id": meta["device_id"], "name": meta["name"], "area": meta["area"]}


# ---------------------------------------------------------- hourly shapes ---

def hour_profile(rows: list, metric: str) -> list:
    """Average of the hourly averages per local hour of day (24 values)."""
    sums = [0.0] * 24
    counts = [0] * 24
    for r in rows:
        avg, start = r.get(f"{metric}_avg"), _start(r)
        if avg is None or start is None:
            continue
        h = to_local(start).hour
        sums[h] += avg
        counts[h] += 1
    return [(sums[h] / counts[h]) if counts[h] else None for h in range(24)]


def heatmap(rows: list, metric: str, end: datetime, months: int = HEATMAP_MONTHS) -> dict:
    """FR-O7: month (rows, oldest first, ending with `end`'s local month) x
    local hour of day (columns) -> average of the hourly averages."""
    local_end = to_local(end)
    keys = [shift_month(local_end.year, local_end.month, -k) for k in range(months - 1, -1, -1)]
    index = {ym: i for i, ym in enumerate(keys)}
    sums = [[0.0] * 24 for _ in keys]
    counts = [[0] * 24 for _ in keys]
    for r in rows:
        avg, start = r.get(f"{metric}_avg"), _start(r)
        if avg is None or start is None:
            continue
        local = to_local(start)
        i = index.get((local.year, local.month))
        if i is None:
            continue
        sums[i][local.hour] += avg
        counts[i][local.hour] += 1
    values = [[(sums[i][h] / counts[i][h]) if counts[i][h] else None for h in range(24)] for i in range(len(keys))]
    present = [v for row in values for v in row if v is not None]
    return {
        "metric": metric,
        "months": ["%04d-%02d" % ym for ym in keys],
        "values": values,
        "min": min(present) if present else None,
        "max": max(present) if present else None,
        "peak_hour": _peak_hour(hour_profile(rows, metric)),
    }


def _peak_hour(profile: list) -> int | None:
    present = [(v, h) for h, v in enumerate(profile) if v is not None]
    return max(present, key=lambda t: (t[0], -t[1]))[1] if present else None  # ties: earliest hour


def heatmaps(rows: list, end: datetime) -> dict:
    return {m: heatmap(rows, m, end) for m in METRICS}


# --------------------------------------------------------- inquiry report ---

def in_hour_window(local_hour: int, hour_from: int, hour_to: int) -> bool:
    """[hour_from, hour_to) in local hours; crosses midnight when from > to
    (22 -> 6 is 22:00-05:59). from == to means the whole day."""
    if hour_from == hour_to:
        return True
    if hour_from < hour_to:
        return hour_from <= local_hour < hour_to
    return local_hour >= hour_from or local_hour < hour_to


def inquiry_report(
    meta: dict, thresholds: dict, rows: list, heatmap_rows: list,
    start: datetime, end: datetime, hour_from: int, hour_to: int,
) -> dict:
    """UC-16 / FR-O4. rows cover [start, end); heatmap_rows the last 12 months."""
    period_rows = _in_period(rows, start, end)
    inside, outside = [], []
    for r in period_rows:
        (inside if in_hour_window(to_local(_start(r)).hour, hour_from, hour_to) else outside).append(r)
    metrics = {}
    for metric in METRICS:
        stats = thresholds.get(metric)
        metrics[metric] = {
            "inside": metric_summary(inside, metric, stats),
            "outside": metric_summary(outside, metric, stats),
            "profile": hour_profile(period_rows, metric),
        }
    return {
        "location": _location(meta),
        "period": {"start": iso_utc(start), "end": iso_utc(end),
                   "start_local": _local_iso(start), "end_local": _local_iso(end)},
        "hour_from": hour_from,
        "hour_to": hour_to,
        "hours_with_data": len(period_rows),
        "metrics": metrics,
        "episodes": episodes(inside, meta["device_id"], thresholds),
        "heatmaps": heatmaps(heatmap_rows, end - _HOUR),
        "units": dict(environment.METRIC_UNITS),
        "labels": dict(METRIC_LABELS),
        "caveats": list(CAVEATS),
    }


# ------------------------------------------------------------ fact sheet ---

def character(rows: list, metric: str) -> dict:
    """Pollutants: steady / variable / spiky from the coefficient of variation
    of the hourly averages. Temperature and humidity get their range instead -
    a coefficient of variation is meaningless on a scale like degrees C."""
    values = [r.get(f"{metric}_avg") for r in rows if r.get(f"{metric}_avg") is not None]
    if not values:
        return {"label": None, "variation": None, "low": None, "high": None}
    if metric not in POLLUTANTS:
        return {"label": None, "variation": None, "low": min(values), "high": max(values)}
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    cv = (var ** 0.5 / mean) if mean else None
    label = None
    if cv is not None:
        label = "steady" if cv < STEADY_MAX_CV else ("variable" if cv < VARIABLE_MAX_CV else "spiky")
    return {"label": label, "variation": cv, "low": min(values), "high": max(values)}


def daily_series(rows: list, metric: str, stats: dict | None,
                 first_day: date | None = None, last_day: date | None = None) -> list:
    """One point per local day: event-weighted average, min, max, out-of-range
    hours. With first/last day given, days without data are included as empty
    points - a gap in the data must look like a gap, not be squeezed out of
    the chart's axis (seen live, D55)."""
    days: dict = {}
    for r in rows:
        start = _start(r)
        if start is None or r.get(f"{metric}_avg") is None:
            continue
        days.setdefault(to_local(start).date().isoformat(), []).append(r)
    keys = sorted(days)
    if first_day and last_day:
        keys = [(first_day + timedelta(days=i)).isoformat() for i in range((last_day - first_day).days + 1)]
    out = []
    for day in keys:
        group = days.get(day)
        if not group:
            out.append({"day": day, "average": None, "min": None, "max": None, "out_of_range_hours": 0})
            continue
        summary = metric_summary(group, metric, stats)
        mins = [r.get(f"{metric}_min") for r in group if r.get(f"{metric}_min") is not None]
        maxs = [r.get(f"{metric}_max") for r in group if r.get(f"{metric}_max") is not None]
        out.append({
            "day": day, "average": summary["average"],
            "min": min(mins) if mins else None, "max": max(maxs) if maxs else None,
            "out_of_range_hours": summary["out_of_range_hours"],
        })
    return out


def fact_sheet(meta: dict, thresholds: dict, rows: list, now: datetime) -> dict:
    """UC-17 / FR-O5. rows cover the last 12 months (the heatmap); the
    per-metric figures use the last 30 days of them."""
    since = now - timedelta(days=FACT_SHEET_DAYS)
    recent = _in_period(rows, since, now + _HOUR)
    metrics = {}
    for metric in METRICS:
        stats = thresholds.get(metric)
        summary = metric_summary(recent, metric, stats)
        metrics[metric] = {
            **summary,
            "character": character(recent, metric),
            "peak_hour": _peak_hour(hour_profile(recent, metric)),
            "daily": daily_series(recent, metric, stats, to_local(since).date(), to_local(now).date()),
        }
    return {
        "location": {**_location(meta), "lat": meta.get("lat"), "lon": meta.get("lon")},
        "period": {"start": iso_utc(since), "end": iso_utc(now), "days": FACT_SHEET_DAYS},
        "hours_with_data": len(recent),
        "metrics": metrics,
        "heatmaps": heatmaps(rows, now),
        "units": dict(environment.METRIC_UNITS),
        "labels": dict(METRIC_LABELS),
        "caveats": list(CAVEATS),
    }
