import json
import logging

from pyspark.sql import functions as F

logger = logging.getLogger(__name__)


def make_foreach_batch_writer(table: str, keyspace: str, stamp_write_ts: bool = False):
    """Returns a foreachBatch function that appends the batch to the given
    Cassandra table via the spark-cassandra-connector. stamp_write_ts adds a
    write_ts column (once per micro-batch, feeds KPI-2 end-to-end latency) -
    only iot.raw_events has that column; agg_1m/agg_1h do not (a window's
    aggregate has no single meaningful "row write time" the way one event
    does), so this must stay False for those tables or the Cassandra
    connector rejects the write (confirmed: it errors on unknown columns,
    not silently drops them)."""

    def write_batch(batch_df, batch_id: int) -> None:
        if batch_df.rdd.isEmpty():
            return

        enriched = batch_df.withColumn("write_ts", F.current_timestamp()) if stamp_write_ts else batch_df
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
