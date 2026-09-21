from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, StringType, StructField, StructType

# Matches producer/producer/schema.py's build_event() output exactly.
# event_ts/ingest_ts are ISO-8601 UTC strings with millisecond precision
# (e.g. "2026-08-18T10:00:00.000Z"), parsed via to_timestamp() below.
EVENT_SCHEMA = StructType([
    StructField("event_id", StringType(), nullable=False),
    StructField("device_id", StringType(), nullable=False),
    StructField("event_ts", StringType(), nullable=False),
    StructField("ingest_ts", StringType(), nullable=False),
    StructField("source_ts", StringType(), nullable=True),
    StructField("co", StringType(), nullable=False),
    StructField("humidity", StringType(), nullable=False),
    StructField("lpg", StringType(), nullable=False),
    StructField("smoke", StringType(), nullable=False),
    StructField("temp", StringType(), nullable=False),
    StructField("light", BooleanType(), nullable=False),
    StructField("motion", BooleanType(), nullable=False),
    StructField("pressure", StringType(), nullable=False),
    StructField("is_synthetic", BooleanType(), nullable=False),
])

NUMERIC_METRICS = ("co", "humidity", "lpg", "smoke", "temp")

# ISO-8601 with millisecond precision and a literal "Z" suffix, e.g.
# "2026-08-18T10:00:00.000Z" - matches build_event()'s isoformat() + "Z" replace.
_TIMESTAMP_FORMAT = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"


def read_kafka(spark, config):
    """maxOffsetsPerTrigger bounds how much backlog a single micro-batch can
    pull, regardless of how large the backlog has grown (e.g. after this job
    was down for a while and the producer kept publishing). Without this cap,
    the first catch-up trigger after a restart tries to consume the entire
    backlog in one batch - a memory spike far bigger than steady-state ever
    produces, which is exactly what OOM-killed an executor and restarted this
    same query in a loop (see docs/operations.html#p10-1)."""
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", config.kafka_bootstrap_servers)
        .option("subscribe", config.kafka_topic_name)
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", config.max_offsets_per_trigger)
        .option("failOnDataLoss", "false")
        .load()
    )


def parse_and_cast(kafka_df):
    """Kafka raw rows (key/value bytes) -> a typed DataFrame matching the
    producer's canonical event schema, with numeric metrics as double and
    timestamps parsed as Spark TimestampType."""
    parsed = (
        kafka_df.select(F.from_json(F.col("value").cast("string"), EVENT_SCHEMA).alias("event"))
        # from_json returns a null struct for a value that isn't parseable
        # JSON at all (as opposed to valid-but-schema-mismatched JSON, which
        # PERMISSIVE mode tolerates field-by-field) - drop those here, before
        # event.* expands a null struct into an all-null row.
        .filter(F.col("event").isNotNull())
        .select("event.*")
    )

    for metric in NUMERIC_METRICS:
        parsed = parsed.withColumn(metric, F.col(metric).cast("double"))
    parsed = parsed.withColumn("pressure", F.col("pressure").cast("double"))

    parsed = (
        parsed
        .withColumn("event_ts", F.to_timestamp("event_ts", _TIMESTAMP_FORMAT))
        .withColumn("ingest_ts", F.to_timestamp("ingest_ts", _TIMESTAMP_FORMAT))
        # nullable - to_timestamp(null) is null, matching synthetic rows' lack
        # of a real-world collection moment (D38).
        .withColumn("source_ts", F.to_timestamp("source_ts", _TIMESTAMP_FORMAT))
    )

    # Belt-and-braces: a message that parsed as JSON but doesn't actually
    # carry a usable event_id/device_id/event_ts/ingest_ts (missing field, or
    # an event_ts string that didn't match _TIMESTAMP_FORMAT) must still be
    # dropped here. anomaly_state.py's OUTPUT_SCHEMA declares event_ts and
    # ingest_ts non-nullable; letting a null through crashes Arrow's columnar
    # encoder (IllegalStateException: Value at index is null) inside
    # applyInPandasWithState, taking down all three streaming queries in a
    # checkpoint-persistent crash loop that never self-heals since the next
    # restart just resumes at the same poisoned offset. One malformed message
    # on the wire must never be able to do that.
    parsed = parsed.filter(
        F.col("event_id").isNotNull()
        & F.col("device_id").isNotNull()
        & F.col("event_ts").isNotNull()
        & F.col("ingest_ts").isNotNull()
    )
    return parsed
