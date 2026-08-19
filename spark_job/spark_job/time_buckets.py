from pyspark.sql import functions as F

BUCKET_SECONDS = 15 * 60  # 15-minute bucket, matches infra/cassandra/schema/002_raw_events.cql


def with_bucket_start(df):
    """event_ts truncated to the 15-minute mark (UTC) - raw_events partition key."""
    return df.withColumn(
        "bucket_start",
        F.to_timestamp(F.floor(F.unix_timestamp("event_ts") / BUCKET_SECONDS) * BUCKET_SECONDS),
    )


def with_day(df, source_col: str = "window_start"):
    """agg_1m partition key component."""
    return df.withColumn("day", F.to_date(F.col(source_col)))


def with_month(df, source_col: str = "window_start"):
    """agg_1h partition key component."""
    return df.withColumn("month", F.trunc(F.col(source_col), "month"))
