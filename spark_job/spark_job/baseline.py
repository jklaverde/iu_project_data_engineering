from pyspark.sql import functions as F

from .schema import NUMERIC_METRICS

# Ceiling formula only applies to the "safety" gas/smoke metrics, per Sec 5.4's
# own example ("smoke/CO ceiling") - temp/humidity have no physical indoor
# safety-ceiling concept and rely on the sigma rule alone.
CEILING_METRICS = ("co", "smoke", "lpg")


def compute_seed_baseline(spark, csv_path: str, ceiling_safety_multiplier: float):
    """One-time batch read of the real Kaggle CSV, computing per-device mean/std
    (the EWMA seed - see anomaly_state.py) and per-device absolute ceilings for
    the gas/smoke metrics. Returns (baseline, ceilings):
      baseline[device_id][metric] = (mean, std)
      ceilings[device_id][metric] = ceiling_value   (only for CEILING_METRICS)
    """
    df = spark.read.option("header", True).option("inferSchema", True).csv(csv_path)

    agg_exprs = []
    for m in NUMERIC_METRICS:
        agg_exprs += [
            F.avg(m).alias(f"{m}_mean"),
            F.stddev_samp(m).alias(f"{m}_std"),
            F.max(m).alias(f"{m}_max"),
            F.expr(f"percentile_approx({m}, 0.999)").alias(f"{m}_p999"),
        ]

    rows = df.groupBy(F.col("device").alias("device_id")).agg(*agg_exprs).collect()

    baseline = {}
    ceilings = {}
    for r in rows:
        device_id = r["device_id"]
        baseline[device_id] = {
            m: (float(r[f"{m}_mean"]), float(r[f"{m}_std"]) if r[f"{m}_std"] is not None else 0.0)
            for m in NUMERIC_METRICS
        }
        ceilings[device_id] = {
            m: max(float(r[f"{m}_max"]), float(r[f"{m}_p999"])) * ceiling_safety_multiplier
            for m in CEILING_METRICS
        }

    return baseline, ceilings
