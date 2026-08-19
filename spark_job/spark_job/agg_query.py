from pyspark.sql import functions as F

from .anomaly_state import flag_anomalies
from .cassandra_sink import make_foreach_batch_writer
from .schema import NUMERIC_METRICS, parse_and_cast, read_kafka
from .time_buckets import with_day, with_month

_METRICS_WITH_PRESSURE = (*NUMERIC_METRICS, "pressure")


def build_agg_query(
    spark,
    config,
    baseline: dict,
    ceilings: dict,
    *,
    query_name: str,
    table: str,
    window_duration: str,
    watermark: str,
    partition_col_name: str,
):
    raw = read_kafka(spark, config)
    parsed = parse_and_cast(raw)
    flagged = flag_anomalies(parsed, baseline, ceilings, config.anomaly_sigma_n, config.anomaly_ewma_alpha)

    metric_aggs = []
    for m in _METRICS_WITH_PRESSURE:
        metric_aggs += [
            F.avg(m).alias(f"{m}_avg"),
            F.min(m).alias(f"{m}_min"),
            F.max(m).alias(f"{m}_max"),
        ]

    windowed = (
        flagged
        .withWatermark("event_ts", watermark)
        .groupBy(F.window("event_ts", window_duration).alias("window"), F.col("device_id"))
        .agg(
            F.count("*").alias("event_count"),
            F.sum(F.col("is_anomaly").cast("long")).alias("anomaly_count"),
            *metric_aggs,
            F.sum(F.col("light").cast("long")).alias("light_active_count"),
            F.sum(F.col("motion").cast("long")).alias("motion_active_count"),
        )
        .withColumn("window_start", F.col("window.start"))
        .withColumn("window_end", F.col("window.end"))
        .withColumn("light_active_ratio", F.col("light_active_count") / F.col("event_count"))
        .withColumn("motion_active_ratio", F.col("motion_active_count") / F.col("event_count"))
        .drop("window")
    )

    if partition_col_name == "day":
        windowed = with_day(windowed)
    else:
        windowed = with_month(windowed)

    return (
        windowed.writeStream
        .queryName(query_name)
        .outputMode("update")
        .foreachBatch(make_foreach_batch_writer(table, config.cassandra_keyspace))
        .option("checkpointLocation", f"{config.checkpoint_root}/{table}")
        .trigger(processingTime=config.trigger_interval)
        .start()
    )
