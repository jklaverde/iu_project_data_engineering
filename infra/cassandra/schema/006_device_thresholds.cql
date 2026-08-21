-- Per-device, per-metric reference statistics for the environmental/planner role's
-- threshold/AQI logic (R1). Deliberately NOT a new set of invented "safety limits" -
-- populated once at startup by spark_job (spark_job/spark_job/main.py, right after
-- compute_seed_baseline() runs) from the exact same BaselineStats already used to seed
-- the streaming anomaly detector (spark_job/spark_job/anomaly_state.py). One source of
-- truth: the map's "critical" status and Spark's own is_anomaly flag agree by
-- construction for the same device/metric/moment.
CREATE TABLE IF NOT EXISTS iot.device_thresholds (
    device_id  text,
    metric     text,
    mean       double,
    stddev     double,
    ceiling    double,
    PRIMARY KEY (device_id, metric)
);
