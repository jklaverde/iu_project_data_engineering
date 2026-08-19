from .anomaly_state import flag_anomalies
from .cassandra_sink import make_foreach_batch_writer
from .schema import parse_and_cast, read_kafka
from .time_buckets import with_bucket_start


def build_raw_query(spark, config, baseline: dict, ceilings: dict, latency_tracker=None):
    raw = read_kafka(spark, config)
    parsed = parse_and_cast(raw)
    flagged = flag_anomalies(parsed, baseline, ceilings, config.anomaly_sigma_n, config.anomaly_ewma_alpha)
    bucketed = with_bucket_start(flagged)

    return (
        bucketed.writeStream
        .queryName("raw_events")
        .outputMode("append")
        .foreachBatch(make_foreach_batch_writer(
            "raw_events", config.cassandra_keyspace, stamp_write_ts=True, latency_tracker=latency_tracker
        ))
        .option("checkpointLocation", f"{config.checkpoint_root}/raw_events")
        .trigger(processingTime=config.trigger_interval)
        .start()
    )
