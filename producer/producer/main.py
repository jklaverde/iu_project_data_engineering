import json
import logging

from .config import load_config
from .device_stats import compute_baseline_stats
from .kafka_client import KafkaEventPublisher
from .logging_setup import configure_logging
from .rate_limiter import RateLimiter
from .replay import run_replay
from .state import ProducerState
from .state_server import start_state_server
from .synthetic import run_synthetic

logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()
    configure_logging(config.log_level)

    logger.info(json.dumps({
        "event": "producer_starting",
        "kafka_bootstrap_servers": config.kafka_bootstrap_servers,
        "kafka_topic": config.kafka_topic_name,
        "rate_msgs_per_sec": config.rate_msgs_per_sec,
        "anomaly_probability": config.anomaly_probability,
        "anomaly_sigma_multiplier": config.anomaly_sigma_multiplier,
        "replay_row_limit": config.replay_row_limit,
    }))

    stats = compute_baseline_stats(config.dataset_csv_path)
    logger.info(json.dumps({
        "event": "baseline_stats_computed",
        "device_ids": stats.device_ids,
        "total_rows": stats.total_rows,
    }))

    state = ProducerState(configured_rate=config.rate_msgs_per_sec, kafka_topic=config.kafka_topic_name)
    start_state_server(state, config.state_http_port)

    publisher = KafkaEventPublisher(config.kafka_bootstrap_servers)
    rate_limiter = RateLimiter(config.rate_msgs_per_sec)

    try:
        run_replay(
            csv_path=config.dataset_csv_path,
            row_limit=config.replay_row_limit,
            stats=stats,
            publisher=publisher,
            topic=config.kafka_topic_name,
            rate_limiter=rate_limiter,
            state=state,
        )
        run_synthetic(
            stats=stats,
            anomaly_probability=config.anomaly_probability,
            anomaly_sigma_multiplier=config.anomaly_sigma_multiplier,
            publisher=publisher,
            topic=config.kafka_topic_name,
            rate_limiter=rate_limiter,
            state=state,
        )
    finally:
        publisher.flush()


if __name__ == "__main__":
    main()
