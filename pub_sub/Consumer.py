""""Kafka subscriber: Thin wrapper around confluent_kafka.Consumer."""
import json
import logging
from typing import Callable, List, Optional

from confluent_kafka import Consumer, KafkaError

from .config import CONSUMER_CONFIG

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, dict], None]  # (topic, decoded_value) -> None


class KafkaSubscriber:
    """
        Subscribe to kafka topics and process messages with handler.

        Usage:
            def handle(topic, msg):
                print(f"[{topic}] {msg}")
            
            sub = KafkaSubscriber(group_id="weather-sensor-group")
            sub.subscribe(["orders"], handler=handle)   # blocks, Ctrl+c to stop
    """

    def __init__(self, group_id: Optional[str] = None, config: Optional[dict] = None):
        cfg = dict(config or CONSUMER_CONFIG)
        if group_id:
            cfg["group.id"] = group_id
        self.consumer = Consumer(cfg)
        self._running = False

    def subscribe(
            self,
            topics: List[str],
            handler: MessageHandler,
            poll_timeout: float = 1.0
    ) -> None:
        """Blocking consume loop. Commits offsets after succesful handling."""
        self._consumer.subscribe(topics)
        self._running = True
        logger.info("Subscribe to %s", topics)
        try:
            while self._running:
                msg = self._consumer.poll(poll_timeout)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue # end of partition, not an error
                    logger.error("Consumer error: %s", msg.error())
                    continue
                try:
                    value = json.loads(msg.value().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.warning("Skipping non-JSON message at offset %d", msg.offset())
                    self._consumer.commit(msg)
                    continue

                handler(msg.topic(), value)
                self._consumer.commit(msg)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.close()



    def stop(self) -> None:
        """Signal the consume loop to exit (e.g., from another thread)."""
        self._running = False

    def close(self) -> None:
        self._consumer.close()
        logger.info("Consumer closed")