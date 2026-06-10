import json
import logging
from typing import Any, Optional

from confluent_kafka import Producer

from .config import PRODUCER_CONFIG

logger = logging.getLogger(__name__)


class KafkaPublisher:
    """Publish JSON-serializable messages to Kafka topics.

    Usage:
        pub = KafkaPublisher()
        pub.publish("orders", {"id":1, "amount":99.5}, key="order-1")
        pub.flush() # call before program exit
    """

    def __init__(self, config: Optional[dict] = None):
        self._producer = Producer(config or PRODUCER_CONFIG)

    
    def publish(self, topic:str, value: Any, key: Optional[str] = None) -> None:
        """
            Asynchronously publish a message. Value is JSON-encoded
        """
        payload = json.dumps(value).encode("utf-8")
        self._producer.produce(
            topic=topic,
            value=payload,
            key=key.encode("utf-8") if key else None,
            callback=self._delivery_report,
        )
        # serve delivery callbacks without blocking
        self._producer.poll(0)

    def flush(self, timeout:float=10.0) -> int:
        """"
            Block until all buffered messages are delivered. Return # still pending
        """
        return self._producer.flush(timeout)
    
    @staticmethod
    def _delivery_report(err, msg) -> None:
        if err is not None:
            logger.error("Delivery failed for %s: %s", msg.topic(), err)
        else:
            logger.debug(
                "Delivered to %s [partition %d] @ offset %d",
                msg.topic(), msg.partition(), msg.offset(),
            )

    # context-manager support: with KafkaPublisher() as pub:.. 
    def __enter__(self) -> "KafkaPublisher":
        return self
    
    def __exit__(self, exc_type, exec, tb) -> None:
        self.flush()