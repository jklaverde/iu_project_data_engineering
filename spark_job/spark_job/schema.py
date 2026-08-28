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
    parsed = kafka_df.select(
        F.from_json(F.col("value").cast("string"), EVENT_SCHEMA).alias("event")
    ).select("event.*")

    for metric in NUMERIC_METRICS:
        parsed = parsed.withColumn(metric, F.col(metric).cast("double"))
    parsed = parsed.withColumn("pressure", F.col("pressure").cast("double"))

    parsed = (
        parsed
        .withColumn("event_ts", F.to_timestamp("event_ts", _TIMESTAMP_FORMAT))
        .withColumn("ingest_ts", F.to_timestamp("ingest_ts", _TIMESTAMP_FORMAT))
    )
    return parsed
