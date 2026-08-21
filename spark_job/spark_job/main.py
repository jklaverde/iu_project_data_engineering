import json
import logging

from pyspark.sql import SparkSession

from .agg_query import build_agg_query
from .baseline import compute_seed_baseline
from .config import load_config
from .device_thresholds_sink import write_device_thresholds
from .latency_tracker import LatencyTracker
from .logging_setup import configure_logging
from .query_progress import QueryProgressTracker, make_listener
from .raw_query import build_raw_query
from .state_server import start_state_server

logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()
    configure_logging(config.log_level)

    logger.info(json.dumps({
        "event": "spark_job_starting",
        "kafka_bootstrap_servers": config.kafka_bootstrap_servers,
        "kafka_topic": config.kafka_topic_name,
        "trigger_interval": config.trigger_interval,
        "watermark_1m": config.watermark_1m,
        "watermark_1h": config.watermark_1h,
        "agg_1h_window_duration": config.agg_1h_window_duration,
        "anomaly_sigma_n": config.anomaly_sigma_n,
        "anomaly_ewma_alpha": config.anomaly_ewma_alpha,
    }))

    spark = SparkSession.builder.appName("iot-sensor-pipeline").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    baseline, ceilings = compute_seed_baseline(
        spark, config.baseline_csv_path, config.anomaly_ceiling_safety_multiplier
    )
    logger.info(json.dumps({
        "event": "baseline_computed",
        "device_ids": sorted(baseline.keys()),
        "ceilings": ceilings,
    }))
    write_device_thresholds(spark, baseline, ceilings, config.cassandra_keyspace)

    tracker = QueryProgressTracker()
    latency_tracker = LatencyTracker()
    spark.streams.addListener(make_listener(tracker))
    start_state_server(tracker, latency_tracker, config.state_http_port)

    raw_query = build_raw_query(spark, config, baseline, ceilings, latency_tracker=latency_tracker)

    agg_1m_query = build_agg_query(
        spark, config, baseline, ceilings,
        query_name="agg_1m", table="agg_1m",
        window_duration="1 minute", watermark=config.watermark_1m,
        partition_col_name="day",
    )

    agg_1h_query = build_agg_query(
        spark, config, baseline, ceilings,
        query_name="agg_1h", table="agg_1h",
        window_duration=config.agg_1h_window_duration, watermark=config.watermark_1h,
        partition_col_name="month",
    )

    logger.info(json.dumps({
        "event": "queries_started",
        "queries": [raw_query.name, agg_1m_query.name, agg_1h_query.name],
    }))

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
