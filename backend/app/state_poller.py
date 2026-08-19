import asyncio
import json
import logging
from datetime import datetime, timezone

from .cassandra_client import CassandraReader
from .config import Config
from .kafka_client import KafkaReader
from .upstream_http import check_url, fetch_json
from .ws_manager import ConnectionManager

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_event_ts(event: dict) -> datetime | None:
    raw = event.get("event_ts")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_kafka_step(watermarks: dict, spark_queries: dict) -> dict:
    per_query = {}
    for name, progress in (spark_queries or {}).items():
        consumed = progress.get("kafka_consumed_offsets") or {}
        lag_per_partition = {}
        total_lag = 0
        for partition, broker_offset in watermarks.items():
            consumed_offset = consumed.get(partition, 0)
            partition_lag = max(broker_offset - consumed_offset, 0)
            lag_per_partition[partition] = partition_lag
            total_lag += partition_lag
        per_query[name] = {
            "consumed_offsets": consumed,
            "lag_per_partition": lag_per_partition,
            "total_lag": total_lag,
        }
    return {"produced_offsets": watermarks, "queries": per_query}


class StatePoller:
    """Owns the two background asyncio loops that assemble the pipeline-state
    snapshot the web app shows (FR-W1-W3): a fast loop for ingestion/kafka/
    spark/cassandra/summary, and a slower loop for the deployment health grid
    (UC-1), which doesn't need second-by-second freshness."""

    def __init__(self, config: Config, kafka_reader: KafkaReader, cassandra_reader: CassandraReader, ws_manager: ConnectionManager):
        self._config = config
        self._kafka_reader = kafka_reader
        self._cassandra_reader = cassandra_reader
        self._ws_manager = ws_manager
        self._lock = asyncio.Lock()
        self._snapshot: dict = {
            "deployment": None,
            "ingestion": None,
            "kafka": None,
            "spark": None,
            "cassandra": None,
            "summary": None,
        }
        self._tasks: list[asyncio.Task] = []
        self._last_producer_state: dict = {}
        self._last_spark_state: dict = {}

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._loop(self._refresh_fast, self._config.poll_interval_seconds)),
            asyncio.create_task(self._loop(self._refresh_deployment, self._config.health_check_interval_seconds)),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def get_snapshot(self) -> dict:
        async with self._lock:
            return dict(self._snapshot)

    async def _loop(self, refresh, interval_seconds: float) -> None:
        while True:
            try:
                await refresh()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(json.dumps({"event": "state_poller_refresh_failed", "refresh": refresh.__name__}))
            await asyncio.sleep(interval_seconds)

    async def _refresh_fast(self) -> None:
        producer_state_fresh, spark_state_fresh = await asyncio.gather(
            fetch_json(f"{self._config.producer_state_url}/state"),
            fetch_json(f"{self._config.spark_job_state_url}/state"),
        )
        # Fall back to the last-known-good snapshot when an upstream is
        # briefly unreachable (e.g. a container restart mid-session) - keeps
        # the response shape stable so the frontend never has to guess which
        # fields exist. `source_reachable` still reflects the CURRENT poll,
        # so the UI can tell live data from a stale echo. Confirmed necessary
        # by actually restarting producer mid-session and observing the
        # frontend crash on a since-fixed assumption that these fields are
        # always present.
        if producer_state_fresh is not None:
            self._last_producer_state = producer_state_fresh
        if spark_state_fresh is not None:
            self._last_spark_state = spark_state_fresh

        recent_events = self._kafka_reader.get_recent_events()
        reference_timestamps = [ts for ts in (_parse_event_ts(ev) for ev in recent_events) if ts is not None]
        watermarks, cassandra_rows = await asyncio.gather(
            asyncio.to_thread(self._kafka_reader.get_watermark_offsets),
            asyncio.to_thread(self._cassandra_reader.recent_raw_events_sync, reference_timestamps),
        )

        ingestion = {
            **self._last_producer_state,
            "recent_events": recent_events,
            "source_reachable": producer_state_fresh is not None,
        }
        kafka_step = _compute_kafka_step(watermarks, self._last_spark_state.get("queries"))
        spark_step = {"queries": {}, "latency": {}, **self._last_spark_state}
        cassandra_step = {"recent_raw_events": cassandra_rows}
        summary_step = {
            "grafana_port": self._config.grafana_port,
            "totals": {
                "events_ingested": self._last_producer_state.get("events_sent_total", 0),
                "anomalies_detected": self._last_producer_state.get("anomalies_injected_total", 0),
                "rows_in_cassandra_sample": len(cassandra_rows),
            },
        }

        async with self._lock:
            self._snapshot["ingestion"] = ingestion
            self._snapshot["kafka"] = kafka_step
            self._snapshot["spark"] = spark_step
            self._snapshot["cassandra"] = cassandra_step
            self._snapshot["summary"] = summary_step
            snapshot = dict(self._snapshot)

        await self._ws_manager.broadcast({"type": "pipeline-state", "data": snapshot})

    async def _refresh_deployment(self) -> None:
        kafka_ok, kafka_detail = await asyncio.to_thread(self._kafka_reader.health_check)
        cassandra_ok, cassandra_detail = await asyncio.to_thread(self._cassandra_reader.health_check_sync)
        probes = await asyncio.gather(
            check_url("http://spark-master:8080/"),
            check_url("http://spark-worker:8081/"),
            check_url(f"{self._config.spark_job_state_url}/healthz"),
            check_url(f"{self._config.producer_state_url}/healthz"),
            check_url("http://prometheus:9090/-/healthy"),
            check_url("http://grafana:3000/api/health"),
            check_url("http://kafka-exporter:9308/metrics"),
            check_url("http://node-exporter:9100/metrics"),
        )
        names = [
            "spark-master", "spark-worker", "spark-job", "producer",
            "prometheus", "grafana", "kafka-exporter", "node-exporter",
        ]
        services = [
            {"name": "kafka", "healthy": kafka_ok, "detail": kafka_detail, "latency_ms": None},
            {"name": "cassandra", "healthy": cassandra_ok, "detail": cassandra_detail, "latency_ms": None},
        ] + [
            {"name": name, "healthy": ok, "detail": detail, "latency_ms": round(latency_ms, 1)}
            for name, (ok, detail, latency_ms) in zip(names, probes)
        ]

        deployment_step = {
            "checked_at": _now_iso(),
            "all_healthy": all(s["healthy"] for s in services),
            "services": services,
        }

        async with self._lock:
            self._snapshot["deployment"] = deployment_step
            snapshot = dict(self._snapshot)

        await self._ws_manager.broadcast({"type": "pipeline-state", "data": snapshot})
