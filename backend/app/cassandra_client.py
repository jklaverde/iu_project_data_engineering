import json
import logging
from datetime import date, datetime, timedelta, timezone

from cassandra.cluster import Cluster

logger = logging.getLogger(__name__)

BUCKET_SECONDS = 15 * 60  # must match spark_job/spark_job/time_buckets.py

RAW_EVENTS_COLUMNS = (
    "device_id, bucket_start, event_ts, event_id, ingest_ts, write_ts, "
    "co, humidity, lpg, smoke, temp, light, motion, pressure, "
    "is_synthetic, is_anomaly, anomaly_reason"
)

AGG_COLUMNS = (
    "device_id, window_start, window_end, event_count, anomaly_count, "
    "co_avg, co_min, co_max, humidity_avg, humidity_min, humidity_max, "
    "lpg_avg, lpg_min, lpg_max, smoke_avg, smoke_min, smoke_max, "
    "temp_avg, temp_min, temp_max, pressure_avg, pressure_min, pressure_max, "
    "light_active_count, light_active_ratio, motion_active_count, motion_active_ratio"
)


def _bucket_start(ts: datetime) -> datetime:
    epoch = int(ts.timestamp())
    floored = (epoch // BUCKET_SECONDS) * BUCKET_SECONDS
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _iso(ts) -> str | None:
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z") if ts else None


def _days_between(start: datetime, end: datetime) -> list:
    days = []
    d = start.date()
    while d <= end.date():
        days.append(d)
        d += timedelta(days=1)
    return days


def _months_between(start: datetime, end: datetime) -> list:
    months = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _agg_row_to_dict(row) -> dict:
    return {
        "device_id": row.device_id,
        "window_start": _iso(row.window_start),
        "window_end": _iso(row.window_end),
        "event_count": row.event_count,
        "anomaly_count": row.anomaly_count,
        "co_avg": row.co_avg, "co_min": row.co_min, "co_max": row.co_max,
        "humidity_avg": row.humidity_avg, "humidity_min": row.humidity_min, "humidity_max": row.humidity_max,
        "lpg_avg": row.lpg_avg, "lpg_min": row.lpg_min, "lpg_max": row.lpg_max,
        "smoke_avg": row.smoke_avg, "smoke_min": row.smoke_min, "smoke_max": row.smoke_max,
        "temp_avg": row.temp_avg, "temp_min": row.temp_min, "temp_max": row.temp_max,
        "pressure_avg": row.pressure_avg, "pressure_min": row.pressure_min, "pressure_max": row.pressure_max,
        "light_active_count": row.light_active_count, "light_active_ratio": row.light_active_ratio,
        "motion_active_count": row.motion_active_count, "motion_active_ratio": row.motion_active_ratio,
    }


def _row_to_dict(row) -> dict:
    return {
        "device_id": row.device_id,
        "bucket_start": _iso(row.bucket_start),
        "event_ts": _iso(row.event_ts),
        "event_id": str(row.event_id),
        "ingest_ts": _iso(row.ingest_ts),
        "write_ts": _iso(row.write_ts),
        "co": row.co,
        "humidity": row.humidity,
        "lpg": row.lpg,
        "smoke": row.smoke,
        "temp": row.temp,
        "light": row.light,
        "motion": row.motion,
        "pressure": row.pressure,
        "is_synthetic": row.is_synthetic,
        "is_anomaly": row.is_anomaly,
        "anomaly_reason": row.anomaly_reason,
    }


class CassandraReader:
    """Read-only Cassandra access for the web app (UC-2 recent rows, UC-6
    anomaly drill-down). AllowAllAuthenticator is in effect locally (see
    infra/cassandra config), so no driver credentials are needed."""

    def __init__(self, host: str, port: int, keyspace: str, known_device_ids: list):
        self._host = host
        self._port = port
        self._keyspace = keyspace
        self._known_device_ids = known_device_ids
        self._cluster: Cluster | None = None
        self._session = None

    def start(self) -> None:
        self._cluster = Cluster([self._host], port=self._port)
        self._session = self._cluster.connect(self._keyspace)
        logger.info(json.dumps({"event": "cassandra_reader_started", "host": self._host}))

    def stop(self) -> None:
        if self._cluster:
            self._cluster.shutdown()

    def health_check_sync(self) -> tuple[bool, str]:
        try:
            row = self._session.execute("SELECT release_version FROM system.local").one()
            return True, f"cassandra {row.release_version}"
        except Exception as exc:
            return False, str(exc)

    def recent_raw_events_sync(self, reference_timestamps: list | None = None, limit: int = 10) -> list:
        """Single-partition point reads only - full partition key
        (device_id, bucket_start) is always supplied, no ALLOW FILTERING.

        bucket_start is derived from each row's own event_ts (see
        spark_job/spark_job/time_buckets.py), NOT wall-clock time - during
        REPLAY mode event_ts comes from the historical Kaggle dataset (e.g.
        2020), so guessing buckets from datetime.now() would silently miss
        every row until hand-over to synthetic mode (confirmed by actually
        running this against a live replay session, not assumed). Pass in
        event_ts values sampled from Kafka (kafka_reader.get_recent_events())
        so the buckets queried always match what's actually being written
        right now; falls back to wall-clock buckets only when no samples are
        available yet (e.g. at cold start)."""
        if reference_timestamps:
            buckets = {_bucket_start(ts) for ts in reference_timestamps}
        else:
            now = datetime.now(timezone.utc)
            buckets = {_bucket_start(now), _bucket_start(now - timedelta(seconds=BUCKET_SECONDS))}
        rows = []
        for device_id in self._known_device_ids:
            for bucket in buckets:
                stmt = (
                    f"SELECT {RAW_EVENTS_COLUMNS} FROM raw_events "
                    f"WHERE device_id=%s AND bucket_start=%s LIMIT {limit}"
                )
                result = self._session.execute(stmt, (device_id, bucket))
                rows.extend(_row_to_dict(r) for r in result)
        rows.sort(key=lambda r: r["event_ts"] or "", reverse=True)
        return rows[:limit]

    def anomalies_sync(self, device_id: str | None, since_minutes: int, limit: int) -> list:
        """Reuses the exact CQL shape already tested in
        infra/grafana/provisioning/dashboards/json/kpi-dashboard.json
        (LIMIT before ALLOW FILTERING - see docs/operations.html#p4-13), just
        selecting the full row so this response is the drill-down target
        directly, no second round trip."""
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        now = datetime.now(timezone.utc)
        device_ids = [device_id] if device_id else self._known_device_ids
        placeholders = ",".join(["%s"] * len(device_ids))
        stmt = (
            f"SELECT {RAW_EVENTS_COLUMNS} FROM raw_events "
            f"WHERE device_id IN ({placeholders}) AND is_anomaly = true "
            f"AND event_ts > %s AND event_ts < %s LIMIT {limit} ALLOW FILTERING"
        )
        params = tuple(device_ids) + (since, now)
        result = self._session.execute(stmt, params)
        rows = [_row_to_dict(r) for r in result]
        rows.sort(key=lambda r: r["event_ts"] or "", reverse=True)
        return rows[:limit]

    def device_metadata_sync(self) -> list:
        """Tiny static lookup table (one row per known device) - unfiltered
        full-table scan is fine at this size, no partition key involved."""
        result = self._session.execute("SELECT device_id, name, area, lat, lon FROM device_metadata")
        return [
            {"device_id": r.device_id, "name": r.name, "area": r.area, "lat": r.lat, "lon": r.lon}
            for r in result
        ]

    def device_thresholds_sync(self) -> dict:
        """Returns {device_id: {metric: {mean, stddev, ceiling}}}. Populated by
        spark_job at startup from the same BaselineStats that seed the
        streaming anomaly detector (spark_job/spark_job/anomaly_state.py) -
        one source of truth for "statistically unusual" vs. "environmentally
        in the warning/critical band"."""
        result = self._session.execute("SELECT device_id, metric, mean, stddev, ceiling FROM device_thresholds")
        out: dict = {}
        for r in result:
            out.setdefault(r.device_id, {})[r.metric] = {
                "mean": r.mean, "stddev": r.stddev, "ceiling": r.ceiling,
            }
        return out

    def latest_reading_sync(self, device_id: str) -> dict | None:
        """Single-partition point reads on the current and previous 15-minute
        bucket (same derivation as recent_raw_events_sync); safe to use
        wall-clock buckets directly since D28 (replay event_ts now tracks
        real time throughout, not just after synthetic hand-over)."""
        now = datetime.now(timezone.utc)
        for bucket in (_bucket_start(now), _bucket_start(now - timedelta(seconds=BUCKET_SECONDS))):
            stmt = (
                f"SELECT {RAW_EVENTS_COLUMNS} FROM raw_events "
                f"WHERE device_id=%s AND bucket_start=%s LIMIT 1"
            )
            row = self._session.execute(stmt, (device_id, bucket)).one()
            if row is not None:
                return _row_to_dict(row)
        return None

    def aggregates_sync(self, device_id: str, granularity: str, since_hours: float, limit: int) -> list:
        """granularity is "1m" (agg_1m, partitioned by (device_id, day)) or
        "1h" (agg_1h, partitioned by (device_id, month)). Spans however many
        day/month partitions the requested window touches - single-partition
        reads per partition, window_start range filter on the clustering
        column (no ALLOW FILTERING needed)."""
        table = "agg_1m" if granularity == "1m" else "agg_1h"
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=since_hours)

        if granularity == "1m":
            partition_col, partition_values = "day", _days_between(since, now)
        else:
            partition_col, partition_values = "month", _months_between(since, now)

        rows = []
        for value in partition_values:
            stmt = (
                f"SELECT {AGG_COLUMNS} FROM {table} "
                f"WHERE device_id=%s AND {partition_col}=%s "
                f"AND window_start >= %s AND window_start <= %s"
            )
            result = self._session.execute(stmt, (device_id, value, since, now))
            rows.extend(_agg_row_to_dict(r) for r in result)
        rows.sort(key=lambda r: r["window_start"] or "", reverse=True)
        return rows[:limit]
