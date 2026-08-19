import json
import logging

from pyspark.sql import functions as F

logger = logging.getLogger(__name__)


def make_foreach_batch_writer(table: str, keyspace: str, stamp_write_ts: bool = False, latency_tracker=None):
    """Returns a foreachBatch function that appends the batch to the given
    Cassandra table via the spark-cassandra-connector. stamp_write_ts adds a
    write_ts column (once per micro-batch, feeds KPI-2 end-to-end latency) -
    only iot.raw_events has that column; agg_1m/agg_1h do not (a window's
    aggregate has no single meaningful "row write time" the way one event
    does), so this must stay False for those tables or the Cassandra
    connector rejects the write (confirmed: it errors on unknown columns,
    not silently drops them). latency_tracker (only passed for raw_events -
    the only table with event_ts/ingest_ts/write_ts all on one row) records
    per-micro-batch end-to-end and per-hop latency percentiles for KPI-2."""

    def write_batch(batch_df, batch_id: int) -> None:
        if batch_df.rdd.isEmpty():
            return

        enriched = batch_df.withColumn("write_ts", F.current_timestamp()) if stamp_write_ts else batch_df

        if latency_tracker is not None:
            # Cast to double (not unix_timestamp(), which truncates to whole
            # seconds) - p50 latency here is well under 1s at low throughput.
            e2e = F.col("write_ts").cast("double") - F.col("event_ts").cast("double")
            hop_produce_to_ingest = F.col("ingest_ts").cast("double") - F.col("event_ts").cast("double")
            hop_ingest_to_write = F.col("write_ts").cast("double") - F.col("ingest_ts").cast("double")

            stats_row = enriched.select(
                F.percentile_approx(e2e, [0.5, 0.95], 1000).alias("e2e_p"),
                F.max(e2e).alias("e2e_max"),
                F.percentile_approx(hop_produce_to_ingest, [0.5, 0.95], 1000).alias("hop1_p"),
                F.percentile_approx(hop_ingest_to_write, [0.5, 0.95], 1000).alias("hop2_p"),
            ).first()

            latency_tracker.record({
                "batch_id": batch_id,
                "e2e_p50_seconds": stats_row["e2e_p"][0],
                "e2e_p95_seconds": stats_row["e2e_p"][1],
                "e2e_max_seconds": stats_row["e2e_max"],
                "hop_produce_to_ingest_p50_seconds": stats_row["hop1_p"][0],
                "hop_produce_to_ingest_p95_seconds": stats_row["hop1_p"][1],
                "hop_ingest_to_write_p50_seconds": stats_row["hop2_p"][0],
                "hop_ingest_to_write_p95_seconds": stats_row["hop2_p"][1],
            })

        row_count = enriched.count()

        (
            enriched.write.format("org.apache.spark.sql.cassandra")
            .options(table=table, keyspace=keyspace)
            .mode("append")
            .save()
        )

        logger.info(json.dumps({
            "event": "batch_written",
            "table": table,
            "batch_id": batch_id,
            "row_count": row_count,
        }))

    return write_batch
