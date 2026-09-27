"""history-backfill Job (D52, REQUIREMENTS.md §5.9, FR-H1/FR-H2).

Run as `python -m app.history_backfill` from the backend image
(k8s/base/job-history-backfill.yaml). One pass:

1. Picks the anchor T0 (the hour the derived timeline ends at) - or reuses
   the one already recorded in iot.history_backfill, so a re-run never
   produces a second, shifted history.
2. Derives a multi-month CSV from the original 8-day Kaggle file by LOOPING
   its 8-day cycle (time of day preserved), sampling one reading per device
   every HISTORY_SAMPLE_MINUTES, shifting temp/humidity along the seasonal
   curve (seasonal.py) and adding a small seeded noise term. The original
   file is never modified. The derived file is what the Dataset Explorer
   serves (dataset_reader.py).
3. Aggregates the same rows into agg_1h - same columns and meaning as the
   Spark job's agg_1h - and writes them straight to Cassandra. Not through
   Kafka/Spark: Spark's watermarks would drop year-old events, and the KPI
   dashboards must keep measuring only the real pipeline.

Idempotent: same anchor + same seed => same file and the same agg_1h primary
keys. When the recorded run is complete, only a missing/mismatched derived
file is regenerated; Cassandra is not touched.
"""

import bisect
import csv
import gc
import itertools
import json
import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args

from . import seasonal
from .logging_setup import configure_logging

logger = logging.getLogger("history_backfill")

NUMERIC_METRICS = ("co", "humidity", "lpg", "smoke", "temp")
CEILING_METRICS = ("co", "smoke", "lpg")  # must match spark_job/spark_job/baseline.py
AGG_METRICS = (*NUMERIC_METRICS, "pressure")

CYCLE_SECONDS = 8 * 86400  # the source file spans 2020-07-12 00:01 .. 2020-07-20 00:03 UTC
META_ID = "default"

# Same simulated-pressure parameters as producer/producer/device_stats.py (D23).
PRESSURE_MEAN, PRESSURE_STD, PRESSURE_MIN, PRESSURE_MAX = 1013.25, 6.0, 980.0, 1040.0

# Noise added to every numeric metric, as a fraction of that device/metric's
# own standard deviation - enough that successive 8-day loops are not exact
# copies, small against the seasonal shift and the anomaly band.
NOISE_FRACTION = 0.05

WRITE_CHUNK = 2000

DERIVED_COLUMNS = ("ts", "source_ts", "device", "co", "humidity", "light", "lpg", "motion", "smoke", "temp", "pressure")


@dataclass(frozen=True)
class Settings:
    cassandra_host: str
    cassandra_port: int
    keyspace: str
    source_csv: str
    derived_csv: str
    span_days: int
    sample_minutes: int
    seed: int
    sigma_n: float
    ceiling_multiplier: float
    wait_seconds: int


def load_settings() -> Settings:
    return Settings(
        cassandra_host=os.environ["CASSANDRA_HOST"],
        cassandra_port=int(os.environ["CASSANDRA_PORT"]),
        keyspace=os.environ["CASSANDRA_KEYSPACE"],
        source_csv=os.getenv("HISTORY_SOURCE_CSV_PATH", "/data/iot_telemetry_data.csv"),
        derived_csv=os.getenv("HISTORY_DERIVED_CSV_PATH", "/data/iot_telemetry_derived.csv"),
        span_days=int(os.getenv("HISTORY_SPAN_DAYS", "770")),
        sample_minutes=int(os.getenv("HISTORY_SAMPLE_MINUTES", "10")),
        seed=int(os.getenv("HISTORY_SEED", "51")),
        sigma_n=float(os.getenv("SPARK_JOB_ANOMALY_SIGMA_N", "3.0")),
        ceiling_multiplier=float(os.getenv("SPARK_JOB_ANOMALY_CEILING_SAFETY_MULTIPLIER", "1.5")),
        wait_seconds=int(os.getenv("HISTORY_WAIT_SECONDS", "900")),
    )


def _log(event: str, **fields) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


# --------------------------------------------------------------------------
# Source data and baseline
# --------------------------------------------------------------------------

@dataclass
class DeviceSource:
    ts: list        # ascending source epoch seconds
    rows: list      # parallel: (co, humidity, lpg, smoke, temp, light, motion)
    mean: dict      # metric -> mean
    std: dict       # metric -> sample std (same as Spark's stddev_samp)
    ceiling: dict   # CEILING_METRICS -> ceiling


def _quantile(sorted_values: list, q: float) -> float:
    idx = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[idx]


def load_source(path: str, ceiling_multiplier: float) -> tuple[dict, float]:
    """Per-device readings plus the same baseline Spark seeds from
    (spark_job/spark_job/baseline.py): mean, sample std, and a ceiling of
    max(max, p99.9) * multiplier for the gas/smoke metrics. Returns
    (devices, cycle_origin) where cycle_origin is the UTC midnight the
    source file starts on."""
    by_device: dict = {}
    first_ts = None
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = float(row["ts"])
            first_ts = ts if first_ts is None else min(first_ts, ts)
            d = by_device.setdefault(row["device"], ([], []))
            d[0].append(ts)
            d[1].append((
                float(row["co"]), float(row["humidity"]), float(row["lpg"]),
                float(row["smoke"]), float(row["temp"]),
                row["light"].strip().lower() == "true",
                row["motion"].strip().lower() == "true",
            ))

    devices = {}
    for device_id, (ts_list, rows) in by_device.items():
        order = sorted(range(len(ts_list)), key=ts_list.__getitem__)
        ts_sorted = [ts_list[i] for i in order]
        rows_sorted = [rows[i] for i in order]
        mean, std, ceiling = {}, {}, {}
        for i, m in enumerate(NUMERIC_METRICS):
            values = [r[i] for r in rows_sorted]
            n = len(values)
            mu = sum(values) / n
            var = sum((v - mu) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
            mean[m], std[m] = mu, math.sqrt(var)
            if m in CEILING_METRICS:
                s = sorted(values)
                ceiling[m] = max(s[-1], _quantile(s, 0.999)) * ceiling_multiplier
        devices[device_id] = DeviceSource(ts_sorted, rows_sorted, mean, std, ceiling)

    cycle_origin = math.floor(first_ts / 86400) * 86400
    return devices, cycle_origin


def _nearest(ts_list: list, target: float) -> int:
    i = bisect.bisect_left(ts_list, target)
    if i == 0:
        return 0
    if i >= len(ts_list):
        return len(ts_list) - 1
    return i if ts_list[i] - target < target - ts_list[i - 1] else i - 1


# --------------------------------------------------------------------------
# Derivation + aggregation
# --------------------------------------------------------------------------

class HourAgg:
    __slots__ = ("count", "anomalies", "sums", "mins", "maxs", "light", "motion")

    def __init__(self):
        self.count = 0
        self.anomalies = 0
        self.sums = {m: 0.0 for m in AGG_METRICS}
        self.mins = {m: math.inf for m in AGG_METRICS}
        self.maxs = {m: -math.inf for m in AGG_METRICS}
        self.light = 0
        self.motion = 0

    def add(self, values: dict, light: bool, motion: bool, is_anomaly: bool) -> None:
        self.count += 1
        self.anomalies += int(is_anomaly)
        for m in AGG_METRICS:
            v = values[m]
            self.sums[m] += v
            if v < self.mins[m]:
                self.mins[m] = v
            if v > self.maxs[m]:
                self.maxs[m] = v
        self.light += int(light)
        self.motion += int(motion)


def _is_anomaly(values: dict, src: DeviceSource, at: datetime, sigma_n: float) -> bool:
    """The §5.4 rule against the seasonal baseline: a ceiling crossing for
    co/lpg/smoke, or |z| > sigma_n where the mean is the July baseline
    shifted to `at` on the seasonal curve - the same band the backend's
    seasonal normal ranges use (environment.py)."""
    for m in NUMERIC_METRICS:
        x = values[m]
        if m in CEILING_METRICS and x > src.ceiling[m]:
            return True
        std = src.std[m]
        if std > 0 and abs(x - (src.mean[m] + seasonal.offset(m, at))) / std > sigma_n:
            return True
    return False


def derive(settings: Settings, devices: dict, cycle_origin: float, anchor: datetime) -> tuple[dict, int]:
    """Writes the derived CSV (atomically) and returns ({(device, hour_start): HourAgg}, row_count)."""
    rng = random.Random(settings.seed)
    step = settings.sample_minutes * 60
    end = int(anchor.timestamp())
    start = end - settings.span_days * 86400
    device_ids = sorted(devices)
    hours: dict = {}
    rows_written = 0

    tmp_path = settings.derived_csv + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(DERIVED_COLUMNS)
        for t in range(start, end, step):
            at = datetime.fromtimestamp(t, tz=timezone.utc)
            # t mod 8 days keeps time of day: epoch 0 and cycle_origin are both UTC midnights.
            src_target = cycle_origin + (t % CYCLE_SECONDS)
            hour_start = t - (t % 3600)
            for device_id in device_ids:
                src = devices[device_id]
                i = _nearest(src.ts, src_target)
                co, humidity, lpg, smoke, temp, light, motion = src.rows[i]
                values = {"co": co, "humidity": humidity, "lpg": lpg, "smoke": smoke, "temp": temp}
                for m in NUMERIC_METRICS:
                    noisy = values[m] + rng.gauss(0.0, NOISE_FRACTION * src.std[m])
                    if m in CEILING_METRICS:
                        noisy = max(noisy, 0.0)
                    values[m] = seasonal.apply(m, noisy, at)
                values["pressure"] = min(max(rng.gauss(PRESSURE_MEAN, PRESSURE_STD), PRESSURE_MIN), PRESSURE_MAX)

                w.writerow((
                    t, repr(src.ts[i]), device_id,
                    repr(values["co"]), repr(values["humidity"]), "true" if light else "false",
                    repr(values["lpg"]), "true" if motion else "false",
                    repr(values["smoke"]), repr(values["temp"]), repr(values["pressure"]),
                ))
                rows_written += 1

                agg = hours.get((device_id, hour_start))
                if agg is None:
                    agg = hours[(device_id, hour_start)] = HourAgg()
                agg.add(values, light, motion, _is_anomaly(values, src, at, settings.sigma_n))

    os.replace(tmp_path, settings.derived_csv)
    return hours, rows_written


def _sidecar_path(settings: Settings) -> str:
    return settings.derived_csv + ".json"


def write_sidecar(settings: Settings, anchor: datetime, rows: int) -> None:
    meta = {
        "anchor_ts": anchor.isoformat(),
        "span_days": settings.span_days,
        "sample_minutes": settings.sample_minutes,
        "seed": settings.seed,
        "rows": rows,
    }
    with open(_sidecar_path(settings), "w", encoding="utf-8") as f:
        json.dump(meta, f)


def derived_file_matches(settings: Settings, anchor: datetime) -> bool:
    try:
        with open(_sidecar_path(settings), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return False
    return (
        os.path.exists(settings.derived_csv)
        and meta.get("anchor_ts") == anchor.isoformat()
        and meta.get("span_days") == settings.span_days
        and meta.get("sample_minutes") == settings.sample_minutes
        and meta.get("seed") == settings.seed
    )


# --------------------------------------------------------------------------
# Cassandra
# --------------------------------------------------------------------------

def wait_for(settings: Settings):
    """Waits for the source CSV (dataset-init) and the history_backfill
    table (cassandra-schema-init) - this Job starts alongside both."""
    deadline = time.monotonic() + settings.wait_seconds
    while not os.path.exists(settings.source_csv):
        if time.monotonic() > deadline:
            sys.exit(f"source CSV {settings.source_csv} never appeared")
        _log("waiting_for_source_csv", path=settings.source_csv)
        time.sleep(10)

    while True:
        try:
            cluster = Cluster([settings.cassandra_host], port=settings.cassandra_port)
            session = cluster.connect(settings.keyspace)
            session.execute("SELECT id FROM history_backfill LIMIT 1")
            return cluster, session
        except Exception as exc:  # NoHostAvailable, InvalidRequest (table missing), ...
            if time.monotonic() > deadline:
                raise
            # NoHostAvailable stringifies as "{}" before Cassandra listens -
            # the type name is what says what is being waited for.
            _log("waiting_for_cassandra_schema", error_type=type(exc).__name__, error=str(exc)[:200])
            try:
                cluster.shutdown()
            except Exception:
                pass
            time.sleep(10)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _months(start: datetime, end: datetime) -> list:
    months, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def existing_live_hours(session, device_ids: list, since: datetime, anchor: datetime) -> set:
    """agg_1h windows already present anywhere in the backfill span - the
    live Spark job can start before this Job, a keyspace that was NOT wiped
    still holds real pipeline output, and a retried attempt finds the rows
    its predecessor wrote. None of them is rewritten. One partition read per device-month
    (~80 for the default span), window_start only."""
    months = _months(since, anchor)
    found = set()
    stmt = session.prepare(
        "SELECT window_start FROM agg_1h WHERE device_id=? AND month=? AND window_start >= ?"
    )
    for device_id in device_ids:
        for month in months:
            for r in session.execute(stmt, (device_id, month, since)):
                found.add((device_id, int(_aware(r.window_start).timestamp())))
    return found


def write_agg_1h(session, hours: dict, skip: set) -> int:
    stmt = session.prepare(
        "INSERT INTO agg_1h (device_id, month, window_start, window_end, event_count, anomaly_count, "
        "co_avg, co_min, co_max, humidity_avg, humidity_min, humidity_max, "
        "lpg_avg, lpg_min, lpg_max, smoke_avg, smoke_min, smoke_max, "
        "temp_avg, temp_min, temp_max, pressure_avg, pressure_min, pressure_max, "
        "light_active_count, light_active_ratio, motion_active_count, motion_active_ratio) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    def params():
        for (device_id, hour_start), a in hours.items():
            if (device_id, hour_start) in skip:
                continue
            ws = datetime.fromtimestamp(hour_start, tz=timezone.utc)
            metric_cols = []
            for m in AGG_METRICS:
                metric_cols += [a.sums[m] / a.count, a.mins[m], a.maxs[m]]
            yield (
                device_id, date(ws.year, ws.month, 1), ws, ws + timedelta(hours=1), a.count, a.anomalies,
                *metric_cols,
                a.light, a.light / a.count, a.motion, a.motion / a.count,
            )

    # Chunked and streamed: building all ~55K parameter tuples plus one
    # result object per insert at once OOM-killed the first live run at the
    # Job's 512Mi limit (D52, local k3d, 2026-09-27).
    written = 0
    it = params()
    while True:
        chunk = list(itertools.islice(it, WRITE_CHUNK))
        if not chunk:
            return written
        for ok, _ in execute_concurrent_with_args(
            session, stmt, chunk, concurrency=32, raise_on_first_error=True, results_generator=True
        ):
            written += int(ok)


def main() -> None:
    configure_logging(os.getenv("BACKEND_LOG_LEVEL", "INFO"))
    settings = load_settings()
    _log("history_backfill_starting", span_days=settings.span_days,
         sample_minutes=settings.sample_minutes, seed=settings.seed)

    cluster, session = wait_for(settings)
    try:
        meta = session.execute(
            "SELECT anchor_ts, span_days, sample_minutes, seed, completed_at FROM history_backfill WHERE id=%s",
            (META_ID,),
        ).one()

        if meta is not None:
            anchor = _aware(meta.anchor_ts)
            if (meta.span_days, meta.sample_minutes, meta.seed) != (
                settings.span_days, settings.sample_minutes, settings.seed
            ):
                # The recorded history was built with other settings; honor
                # what is in Cassandra rather than mixing two derivations.
                _log("settings_differ_from_recorded_run_using_recorded",
                     recorded={"span_days": meta.span_days, "sample_minutes": meta.sample_minutes, "seed": meta.seed})
                settings = Settings(**{**settings.__dict__, "span_days": meta.span_days,
                                       "sample_minutes": meta.sample_minutes, "seed": meta.seed})
        else:
            now = datetime.now(timezone.utc)
            anchor = now.replace(minute=0, second=0, microsecond=0)

        complete = meta is not None and meta.completed_at is not None
        if complete and derived_file_matches(settings, anchor):
            _log("history_backfill_already_complete", anchor_ts=anchor)
            return

        history_start = anchor - timedelta(days=settings.span_days)
        if not complete:
            session.execute(
                "INSERT INTO history_backfill (id, anchor_ts, history_start, span_days, sample_minutes, seed) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (META_ID, anchor, history_start, settings.span_days, settings.sample_minutes, settings.seed),
            )

        devices, cycle_origin = load_source(settings.source_csv, settings.ceiling_multiplier)
        _log("source_loaded", devices=sorted(devices), rows=sum(len(d.ts) for d in devices.values()))

        hours, rows = derive(settings, devices, cycle_origin, anchor)
        device_ids = sorted(devices)
        # The ~405K source rows are not needed past this point; free them
        # before the write phase instead of holding both at the peak.
        del devices
        gc.collect()
        write_sidecar(settings, anchor, rows)
        _log("derived_csv_written", path=settings.derived_csv, rows=rows,
             history_start=history_start, anchor_ts=anchor)

        if complete:
            _log("history_backfill_file_regenerated_only", anchor_ts=anchor)
            return

        skip = existing_live_hours(session, device_ids, history_start, anchor)
        written = write_agg_1h(session, hours, skip)
        session.execute(
            "UPDATE history_backfill SET rows_written=%s, completed_at=%s WHERE id=%s",
            (written, datetime.now(timezone.utc), META_ID),
        )
        # skipped_existing_windows counts hours already present: real pipeline
        # output, or rows an earlier attempt of this same backfill wrote.
        _log("history_backfill_complete", agg_1h_rows=written, skipped_existing_windows=len(skip),
             history_start=history_start, anchor_ts=anchor)
    finally:
        cluster.shutdown()


if __name__ == "__main__":
    main()
