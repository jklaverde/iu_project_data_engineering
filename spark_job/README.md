# Spark job (P3 — processing)

PySpark Structured Streaming job: consumes `sensor-readings` from Kafka,
flags anomalies against an adaptive per-device rolling baseline (§5.4,
FR-S3), writes raw events plus 1-minute/1-hour windowed aggregates to
Cassandra (FR-S1/S2). See the root `REQUIREMENTS.md` and
`docs/PROGRESS.md` for the full pipeline context — normally this runs as
the `spark-job` service in `docker-compose.yml`.

## Architecture

Three independent Structured Streaming queries (`raw_events`, `agg_1m`,
`agg_1h`), each with its own Kafka read and checkpoint, all started from one
`spark-submit` application (`run.py` → `spark_job/main.py`). Anomaly
detection runs identically in each query (adaptive EWMA per device/metric,
seeded from a one-time batch read of the real Kaggle CSV, plus a static
per-device absolute ceiling for the gas/smoke metrics) — see
`spark_job/anomaly_state.py` and `spark_job/baseline.py`.

## Configuration

All configuration is via environment variables — see `.env.example` at the
repo root (`SPARK_JOB_*`). Notable dev-only override, **not** part of the
shipped `.env.example` default: temporarily set `SPARK_JOB_AGG_1H_WINDOW_DURATION=2
minutes` in your local `.env` to verify `agg_1h` output without waiting a
real hour, then reset it to `1 hour`.

## Why a separate `run.py`

`spark-submit` executes the submitted script as `__main__`, outside any
package context — submitting `spark_job/main.py` directly would break its
internal relative imports (`from .config import ...`). `run.py` is a thin
top-level script (sibling of the `spark_job/` package) that just imports and
calls `spark_job.main.main()`, so the package's own modules keep using
normal relative imports.

## Jars

The Kafka and Cassandra connector jars are pre-resolved into the image's Ivy
cache at Docker build time (see the `Dockerfile`) so `spark-submit
--packages` at container runtime never needs network access — required for
`docker compose up -d` to work with no manual steps.
