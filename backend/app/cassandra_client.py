import json
import logging
from datetime import datetime, timedelta, timezone

from cassandra.cluster import Cluster

logger = logging.getLogger(__name__)

BUCKET_SECONDS = 15 * 60  # must match spark_job/spark_job/time_buckets.py

RAW_EVENTS_COLUMNS = (
    "device_id, bucket_start, event_ts, event_id, ingest_ts, write_ts, "
    "co, humidity, lpg, smoke, temp, light, motion, pressure, "
    "is_synthetic, is_anomaly, anomaly_reason"
)


def _bucket_start(ts: datetime) -> datetime:
    epoch = int(ts.timestamp())
    floored = (epoch // BUCKET_SECONDS) * BUCKET_SECONDS
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _iso(ts) -> str | None:
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z") if ts else None


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
        (LIMIT before ALLOW FILTERING - see docs/TROUBLESHOOTING.md), just
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
