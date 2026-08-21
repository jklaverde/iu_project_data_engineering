import json
import logging

from pyspark.sql import Row

logger = logging.getLogger(__name__)


def write_device_thresholds(spark, baseline: dict, ceilings: dict, keyspace: str) -> None:
    """Persists the seeded per-device/per-metric mean/std/ceiling
    (compute_seed_baseline's own output - see baseline.py) into
    iot.device_thresholds, the single source of truth the backend's
    environmental/planner role reads (backend/app/environment.py) so its
    "critical" status agrees with this job's own is_anomaly rule for the
    same device/metric/moment. Runs once at startup; Cassandra INSERT on an
    existing primary key (device_id, metric) is an idempotent overwrite, so
    re-running on restart is safe."""
    rows = []
    for device_id, metrics in baseline.items():
        device_ceilings = ceilings.get(device_id, {})
        for metric, (mean, std) in metrics.items():
            rows.append(Row(
                device_id=device_id,
                metric=metric,
                mean=float(mean),
                stddev=float(std),
                ceiling=float(device_ceilings[metric]) if metric in device_ceilings else None,
            ))

    if not rows:
        return

    df = spark.createDataFrame(rows)
    (
        df.write.format("org.apache.spark.sql.cassandra")
        .options(table="device_thresholds", keyspace=keyspace)
        .mode("append")
        .save()
    )
    logger.info(json.dumps({
        "event": "device_thresholds_written",
        "device_count": len(baseline),
        "row_count": len(rows),
    }))
