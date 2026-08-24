import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kafka_bootstrap_servers: str
    kafka_topic_name: str
    cassandra_host: str
    cassandra_port: int
    cassandra_keyspace: str
    trigger_interval: str
    max_offsets_per_trigger: int
    watermark_1m: str
    watermark_1h: str
    agg_1h_window_duration: str
    anomaly_sigma_n: float
    anomaly_ewma_alpha: float
    anomaly_ceiling_safety_multiplier: float
    baseline_csv_path: str
    checkpoint_root: str
    state_http_port: int
    log_level: str


def load_config() -> Config:
    return Config(
        kafka_bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        kafka_topic_name=os.environ["KAFKA_TOPIC_NAME"],
        cassandra_host=os.environ["CASSANDRA_HOST"],
        cassandra_port=int(os.environ["CASSANDRA_PORT"]),
        cassandra_keyspace=os.environ["CASSANDRA_KEYSPACE"],
        trigger_interval=os.getenv("SPARK_JOB_TRIGGER_INTERVAL", "30 seconds"),
        max_offsets_per_trigger=int(os.getenv("SPARK_JOB_MAX_OFFSETS_PER_TRIGGER", "20000")),
        watermark_1m=os.getenv("SPARK_JOB_WATERMARK_1M", "2 minutes"),
        watermark_1h=os.getenv("SPARK_JOB_WATERMARK_1H", "10 minutes"),
        agg_1h_window_duration=os.getenv("SPARK_JOB_AGG_1H_WINDOW_DURATION", "1 hour"),
        anomaly_sigma_n=float(os.getenv("SPARK_JOB_ANOMALY_SIGMA_N", "3.0")),
        anomaly_ewma_alpha=float(os.getenv("SPARK_JOB_ANOMALY_EWMA_ALPHA", "0.001")),
        anomaly_ceiling_safety_multiplier=float(os.getenv("SPARK_JOB_ANOMALY_CEILING_SAFETY_MULTIPLIER", "1.5")),
        baseline_csv_path=os.getenv("SPARK_JOB_BASELINE_CSV_PATH", "/data/iot_telemetry_data.csv"),
        checkpoint_root=os.getenv("SPARK_JOB_CHECKPOINT_ROOT", "/opt/spark-checkpoints"),
        state_http_port=int(os.getenv("SPARK_JOB_STATE_HTTP_PORT", "8000")),
        log_level=os.getenv("SPARK_JOB_LOG_LEVEL", "INFO"),
    )
