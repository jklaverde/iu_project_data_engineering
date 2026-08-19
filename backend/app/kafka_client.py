import asyncio
import collections
import json
import logging
import threading
import time

from confluent_kafka import Consumer, KafkaException, TopicPartition
from confluent_kafka.admin import AdminClient

logger = logging.getLogger(__name__)

RECENT_EVENTS_MAXLEN = 10


class KafkaReader:
    """Read-only Kafka access for the web app (UC-2: recent event content,
    per-partition broker watermark offsets for lag computation, and a cheap
    health probe). Manual partition assignment, no consumer group, no offset
    commits - this consumer must never influence the real spark-job
    consumer's lag/rebalancing (FR-K2's actual lag comes from the spark-job's
    own reported offsets, not from this reader)."""

    def __init__(self, bootstrap_servers: str, topic: str):
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._admin = AdminClient({"bootstrap.servers": bootstrap_servers})
        self._consumer: Consumer | None = None
        self._recent_events = collections.deque(maxlen=RECENT_EVENTS_MAXLEN)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._consumer = Consumer({
            "bootstrap.servers": self._bootstrap_servers,
            "group.id": f"backend-observer-{int(time.time())}",
            "enable.auto.commit": False,
        })
        metadata = self._admin.list_topics(topic=self._topic, timeout=10)
        partitions = list(metadata.topics[self._topic].partitions.keys())
        self._consumer.assign([
            TopicPartition(self._topic, p, offset=-1)  # OFFSET_END: only new messages from here on
            for p in partitions
        ])
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(json.dumps({"event": "kafka_reader_started", "partitions": partitions}))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._consumer:
            self._consumer.close()

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            msg = self._consumer.poll(timeout=1.0)
            if msg is None or msg.error():
                continue
            try:
                event = json.loads(msg.value())
            except (ValueError, TypeError):
                continue
            with self._lock:
                self._recent_events.append(event)

    def get_recent_events(self) -> list:
        with self._lock:
            return list(reversed(self._recent_events))

    def get_watermark_offsets(self) -> dict:
        """{partition: high_watermark} - the broker-side produced offset per
        partition, used both to sample partition count/health and, combined
        with spark-job's self-reported kafka_consumed_offsets, to compute
        per-query lag the same way Grafana's PromQL panel already does."""
        if self._consumer is None:
            return {}
        metadata = self._admin.list_topics(topic=self._topic, timeout=5)
        offsets = {}
        for partition in metadata.topics[self._topic].partitions.keys():
            _low, high = self._consumer.get_watermark_offsets(
                TopicPartition(self._topic, partition), timeout=5, cached=False
            )
            offsets[str(partition)] = high
        return offsets

    def health_check(self) -> tuple[bool, str]:
        try:
            metadata = self._admin.list_topics(timeout=2)
            if self._topic not in metadata.topics:
                return False, f"topic {self._topic} not found"
            return True, f"{len(metadata.topics)} topics visible"
        except KafkaException as exc:
            return False, str(exc)


async def run_in_thread(func, *args):
    return await asyncio.to_thread(func, *args)
