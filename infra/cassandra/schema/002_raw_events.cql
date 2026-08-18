-- Raw sensor events; partitioned by device + 15-minute bucket to bound partition size
-- for a write-heavy, no-TTL workload (NFR-4). At the 500 msg/s endurance rate across
-- ~3 devices, 15-minute buckets land around ~150K rows / ~30MB per partition, safely
-- under Cassandra's soft partition-size guideline. First cut — exact write shape owned
-- by the P3 Spark job.
CREATE TABLE IF NOT EXISTS iot.raw_events (
    device_id      text,
    bucket_start   timestamp,   -- event_ts truncated to the 15-minute mark (UTC); bounds partition size (NFR-4)
    event_ts       timestamp,
    event_id       uuid,
    ingest_ts      timestamp,   -- stamped by the producer (FR-I3)
    write_ts       timestamp,   -- stamped by the Spark sink at Cassandra write time; feeds KPI-2 end-to-end latency
    co             double,
    humidity       double,
    lpg            double,
    smoke          double,
    temp           double,
    light          boolean,
    motion         boolean,
    pressure       double,      -- simulated for ALL rows (D23); must be labeled synthetic in every UI/Grafana display
    is_synthetic   boolean,     -- true once the producer has handed over to synthetic generation (§5.3, UC-3)
    is_anomaly     boolean,     -- rule-based flag (§5.4 / FR-S3), populated by the Spark job in P3
    anomaly_reason text,        -- e.g. "co > 3sigma" / "smoke ceiling exceeded"; nullable, supports UC-6 traceability
    PRIMARY KEY ((device_id, bucket_start), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id ASC)
  AND comment = 'Raw sensor events; partitioned by device+15min to bound partition size for a write-heavy, no-TTL workload (NFR-4). First cut - exact write shape owned by the P3 Spark job.';
