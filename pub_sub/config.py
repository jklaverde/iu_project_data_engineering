import os

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "my-app-group")

PRODUCER_CONFIG = {
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "acks": "all",                  # wait for all in-sync replicas (durability)
    "enable.idempotence": True,     # avoid duplicates on retries
    "linger.ms": 5,                 # small batching window for throughput
}

CONSUMER_CONFIG = {
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "group.id": DEFAULT_GROUP_ID,
    "auto.offset.reset": "earliest",    # read from beginning if no committed offset
    "enable.auto.commit": False,        # commit manually after processing
}