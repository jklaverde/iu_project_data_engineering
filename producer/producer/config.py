import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kafka_bootstrap_servers: str
    kafka_topic_name: str
    rate_msgs_per_sec: float
    anomaly_probability: float
    anomaly_sigma_multiplier: float
    dataset_csv_path: str
    replay_row_limit: int
    state_http_port: int
    log_level: str


def load_config() -> Config:
    return Config(
        kafka_bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        kafka_topic_name=os.environ["KAFKA_TOPIC_NAME"],
        rate_msgs_per_sec=float(os.getenv("PRODUCER_RATE_MSGS_PER_SEC", "100")),
        anomaly_probability=float(os.getenv("PRODUCER_ANOMALY_PROBABILITY", "0.05")),
        anomaly_sigma_multiplier=float(os.getenv("PRODUCER_ANOMALY_SIGMA_MULTIPLIER", "4.0")),
        dataset_csv_path=os.getenv("PRODUCER_DATASET_CSV_PATH", "/data/iot_telemetry_data.csv"),
        replay_row_limit=int(os.getenv("PRODUCER_REPLAY_ROW_LIMIT", "0")),
        state_http_port=int(os.getenv("PRODUCER_STATE_HTTP_PORT", "8000")),
        log_level=os.getenv("PRODUCER_LOG_LEVEL", "INFO"),
    )
