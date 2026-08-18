-- 1-minute tumbling-window aggregates per device (FR-S2). Wide row per (device, window)
-- so a Grafana panel reading several metrics for the same device/window is a single
-- partition, single-row read. Partitioned by (device_id, day): ~1440 rows/device/day,
-- safely bounded regardless of total retention (NFR-4). First cut - exact columns owned
-- by the P3 Spark job.
CREATE TABLE IF NOT EXISTS iot.agg_1m (
    device_id            text,
    day                  date,
    window_start         timestamp,
    window_end           timestamp,
    event_count          bigint,
    anomaly_count        bigint,
    co_avg                double,
    co_min                double,
    co_max                double,
    humidity_avg          double,
    humidity_min          double,
    humidity_max          double,
    lpg_avg                double,
    lpg_min                double,
    lpg_max                double,
    smoke_avg              double,
    smoke_min              double,
    smoke_max              double,
    temp_avg               double,
    temp_min               double,
    temp_max               double,
    pressure_avg           double,
    pressure_min           double,
    pressure_max           double,
    light_active_count   bigint,
    light_active_ratio   double,
    motion_active_count  bigint,
    motion_active_ratio  double,
    PRIMARY KEY ((device_id, day), window_start)
) WITH CLUSTERING ORDER BY (window_start DESC)
  AND comment = '1-minute tumbling-window aggregates per device (FR-S2). First cut - exact columns owned by the P3 Spark job.';
