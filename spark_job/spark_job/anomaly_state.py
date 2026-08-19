import math

import pandas as pd
from pyspark.sql.streaming.state import GroupStateTimeout
from pyspark.sql.types import BooleanType, DoubleType, StringType, StructField, StructType, TimestampType

from .baseline import CEILING_METRICS
from .schema import NUMERIC_METRICS

MIN_VAR = 1e-12

INPUT_COLUMNS = [
    "event_id", "device_id", "event_ts", "ingest_ts",
    "co", "humidity", "lpg", "smoke", "temp",
    "light", "motion", "pressure", "is_synthetic",
]

STATE_SCHEMA = StructType(
    [StructField(f"{m}_{stat}", DoubleType(), True) for m in NUMERIC_METRICS for stat in ("mean", "var")]
)

OUTPUT_SCHEMA = StructType([
    StructField("event_id", StringType(), False),
    StructField("device_id", StringType(), False),
    StructField("event_ts", TimestampType(), False),
    StructField("ingest_ts", TimestampType(), False),
    StructField("co", DoubleType(), False),
    StructField("humidity", DoubleType(), False),
    StructField("lpg", DoubleType(), False),
    StructField("smoke", DoubleType(), False),
    StructField("temp", DoubleType(), False),
    StructField("light", BooleanType(), False),
    StructField("motion", BooleanType(), False),
    StructField("pressure", DoubleType(), False),
    StructField("is_synthetic", BooleanType(), False),
    StructField("is_anomaly", BooleanType(), False),
    StructField("anomaly_reason", StringType(), True),
])

STATE_TIMEOUT = GroupStateTimeout.NoTimeout


def _seed_means_vars(baseline: dict, device_id: str) -> dict:
    seed = baseline.get(device_id, {})
    result = {}
    for m in NUMERIC_METRICS:
        mean, std = seed.get(m, (0.0, 1.0))
        var = (std ** 2) if std else 1.0
        result[m] = (mean, var if var > 0 else 1.0)
    return result


def make_anomaly_state_func(baseline: dict, ceilings: dict, sigma_n: float, alpha: float):
    """Returns the applyInPandasWithState function: per-device EWMA mean/var
    (seeded from the batch-computed CSV baseline) + a static per-device ceiling
    check, evaluated against each event BEFORE the state is updated with that
    event's own value (Sec 5.4 rolling-mean rule, FR-S3)."""

    def func(key, pdf_iter, state):
        device_id = key[0]

        if state.exists:
            state_row = state.get
            means_vars = {}
            i = 0
            for m in NUMERIC_METRICS:
                means_vars[m] = (state_row[i], state_row[i + 1])
                i += 2
        else:
            means_vars = _seed_means_vars(baseline, device_id)

        device_ceilings = ceilings.get(device_id, {})
        output_frames = []

        for pdf in pdf_iter:
            if len(pdf) == 0:
                continue
            reasons = [[] for _ in range(len(pdf))]

            for m in NUMERIC_METRICS:
                mean, var = means_vars[m]
                ceiling = device_ceilings.get(m) if m in CEILING_METRICS else None
                values = pdf[m].to_numpy()

                for idx in range(len(values)):
                    x = values[idx]
                    if x is None or (isinstance(x, float) and math.isnan(x)):
                        continue

                    std = math.sqrt(max(var, MIN_VAR))
                    z = (x - mean) / std

                    if ceiling is not None and x > ceiling:
                        reasons[idx].append(f"{m}:ceiling({x:.5f}>{ceiling:.5f})")
                    elif abs(z) > sigma_n:
                        reasons[idx].append(f"{m}:sigma({z:.2f}sigma)")

                    delta = x - mean
                    mean = mean + alpha * delta
                    var = (1 - alpha) * (var + alpha * delta * delta)

                means_vars[m] = (mean, var)

            out = pdf[INPUT_COLUMNS].copy()
            out["anomaly_reason"] = [";".join(r) if r else None for r in reasons]
            out["is_anomaly"] = out["anomaly_reason"].notna()
            output_frames.append(out)

        new_state = tuple(v for m in NUMERIC_METRICS for v in means_vars[m])
        state.update(new_state)

        if output_frames:
            yield pd.concat(output_frames, ignore_index=True)
        else:
            yield pd.DataFrame(columns=INPUT_COLUMNS + ["is_anomaly", "anomaly_reason"])

    return func


def flag_anomalies(df, baseline: dict, ceilings: dict, sigma_n: float, alpha: float):
    func = make_anomaly_state_func(baseline, ceilings, sigma_n, alpha)
    return (
        df.groupBy("device_id")
        .applyInPandasWithState(
            func,
            outputStructType=OUTPUT_SCHEMA,
            stateStructType=STATE_SCHEMA,
            outputMode="append",
            timeoutConf=STATE_TIMEOUT,
        )
    )
