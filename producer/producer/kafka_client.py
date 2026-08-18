import json
import logging

from confluent_kafka import Producer

logger = logging.getLogger(__name__)


class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str):
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",
            "enable.idempotence": True,
            "linger.ms": 5,
        })

    def publish(self, topic: str, event: dict, key: str) -> None:
        self._producer.produce(
            topic=topic,
            key=key.encode("utf-8"),
            value=json.dumps(event).encode("utf-8"),
            callback=self._delivery_report,
        )
        self._producer.poll(0)

    @staticmethod
    def _delivery_report(err, msg) -> None:
        if err is not None:
            logger.error(json.dumps({
                "event": "kafka_delivery_failed",
                "topic": msg.topic(),
                "error": str(err),
            }))

    def flush(self, timeout: float = 10.0) -> int:
        return self._producer.flush(timeout)
