import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    kafka_bootstrap_servers: str
    kafka_topic_name: str
    cassandra_host: str
    cassandra_port: int
    cassandra_keyspace: str
    producer_state_url: str
    spark_job_state_url: str
    known_device_ids: list = field(default_factory=list)
    poll_interval_seconds: float = 2.0
    health_check_interval_seconds: float = 5.0
    admin_username: str = "admin"
    admin_password: str = ""
    session_secret: str = ""
    session_ttl_seconds: int = 43200
    cookie_secure: bool = False
    grafana_port: int = 3000
    log_level: str = "INFO"


def load_config() -> Config:
    return Config(
        kafka_bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        kafka_topic_name=os.environ["KAFKA_TOPIC_NAME"],
        cassandra_host=os.environ["CASSANDRA_HOST"],
        cassandra_port=int(os.environ["CASSANDRA_PORT"]),
        cassandra_keyspace=os.environ["CASSANDRA_KEYSPACE"],
        producer_state_url=os.environ["PRODUCER_STATE_URL"],
        spark_job_state_url=os.environ["SPARK_JOB_STATE_URL"],
        known_device_ids=[
            d.strip() for d in os.getenv("BACKEND_KNOWN_DEVICE_IDS", "").split(",") if d.strip()
        ],
        poll_interval_seconds=float(os.getenv("BACKEND_POLL_INTERVAL_SECONDS", "2")),
        health_check_interval_seconds=float(os.getenv("BACKEND_HEALTH_CHECK_INTERVAL_SECONDS", "5")),
        admin_username=os.getenv("BACKEND_ADMIN_USERNAME", "admin"),
        admin_password=os.environ["BACKEND_ADMIN_PASSWORD"],
        session_secret=os.environ["BACKEND_SESSION_SECRET"],
        session_ttl_seconds=int(os.getenv("BACKEND_SESSION_TTL_SECONDS", "43200")),
        cookie_secure=os.getenv("BACKEND_COOKIE_SECURE", "false").lower() == "true",
        grafana_port=int(os.getenv("BACKEND_GRAFANA_PORT", "3000")),
        log_level=os.getenv("BACKEND_LOG_LEVEL", "INFO"),
    )
