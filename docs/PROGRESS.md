# Project Progress / Continuation Notes

Running status doc so a future session (or a different machine) can pick this project
back up without re-deriving context. Update this at the end of each phase. See
`REQUIREMENTS.md` for the frozen v1.0 spec and phase roadmap (§14) — this file tracks
progress *against* that roadmap plus implementation-level decisions the requirements
doc doesn't cover. See `docs/TROUBLESHOOTING.md` for bugs/gotchas found along the way.

---

## Status: P1 and P2 done, committed, pushed. P3 (Spark) is next.

| Phase | What it is | Status |
|---|---|---|
| P1 — Foundation | docker-compose stack: Kafka, Cassandra, Spark (standalone, no job), Prometheus, Grafana | **Done** (commits `cab33ec`, `e0d4d25`) |
| P2 — Ingestion | Producer: Kaggle replay + synthetic hand-over | **Done** (commit `3d141b4`) |
| P3 — Processing | PySpark Structured Streaming job: validation, anomalies, dual windows, Cassandra sink | **Not started** |
| P4 — Observability | Exporters wired, Grafana dashboards provisioned | Not started |
| P5 — Web app | FastAPI read-only API + React guided UI + basic login | Not started |
| P6 — VPS deployment | 3 Contabo VPS, k3s, hardening | Not started |
| P7 — Endurance | 48-hour run against §10 acceptance criteria | Not started |

## Resuming locally

```
docker compose up -d
```
Brings up the full stack (Kafka, Cassandra, Spark standalone, Prometheus, Grafana,
kafka-ui, and the producer) — the producer starts automatically and immediately begins
replaying the Kaggle dataset at 100 msg/s into topic `sensor-readings`. See the root
`README.md` for the verification checklist and `docker compose down` / `down -v`.

If `kaggle_repository/iot_telemetry_data.csv` is missing (it's gitignored, not
committed — see `docs/TROUBLESHOOTING.md`), regenerate it first:
```
python kaggle_repository/download_repository.py
```

## Repo layout (as it stands)

```
docker-compose.yml          root compose file - the whole local stack (FR-D1)
.env / .env.example         all runtime config (FR-D2) - .env is gitignored
infra/
  cassandra/schema/         CQL, applied by the cassandra-schema-init one-shot container
  prometheus/prometheus.yml self-scrape only for now; P4 adds exporter targets
producer/                   P2: the ingestion service (own Dockerfile + requirements.txt)
  producer/                 the importable Python package
docs/
  TROUBLESHOOTING.md        bugs/gotchas log, by phase
  PROGRESS.md                this file
REQUIREMENTS.md             frozen v1.0 spec - do not edit casually, see its own changelog header
```
Each future Python service (the P3 Spark job, the P5 FastAPI backend) is expected to
get its own directory with its own `requirements.txt`, following the `producer/`
pattern — not a shared root dependency file (NFR-10.8's minimal-deps-per-service spirit).

## Implementation decisions made beyond what REQUIREMENTS.md specifies

`REQUIREMENTS.md` is frozen at v1.0 and deliberately doesn't cover implementation
details. These were decided while building P1/P2 and matter for anything downstream
that touches the same surfaces:

**Kafka / Cassandra (P1)**
- Compose project is named `iu-sensor-pipeline` (top-level `name:` in
  `docker-compose.yml`), and no service sets an explicit `container_name:` — this
  namespaces every container to avoid clashing with unrelated Docker projects on a
  shared dev machine (see `docs/TROUBLESHOOTING.md` #3).
- Kafka's actual KRaft log directory had to be pinned via `KAFKA_LOG_DIRS` to match the
  mounted volume (see `docs/TROUBLESHOOTING.md` #2) — if a future change ever revisits
  the `kafka` service definition, do not drop that env var without re-verifying
  persistence across a real `docker compose down && up -d` cycle.
- `raw_events` is partitioned by `(device_id, bucket_start)` where `bucket_start` is a
  **15-minute** bucket (not hourly) — sized for the NFR-2 endurance rate. `agg_1m` /
  `agg_1h` are partitioned by `(device_id, day)` / `(device_id, month)`.
- The `raw_events` table has a few columns beyond the literal §5.2 field list, added
  because they're cheap now and expensive to retrofit once Spark is writing: `write_ts`
  (Spark sink write time, feeds KPI-2 latency), `is_synthetic`, `is_anomaly`,
  `anomaly_reason`. **The producer only ever populates `is_synthetic`** — `write_ts`,
  `is_anomaly`, `anomaly_reason` are null until P3's Spark job populates them. This is
  the exact contract P3 needs to fulfil.
- Grafana gets no default credential — `GF_SECURITY_ADMIN_PASSWORD` is a required env
  var with no fallback (compose refuses to start without it set in `.env`).

**Producer (P2) — the wire contract P3 must consume**
- Kafka message value is JSON with exactly these fields (see
  `producer/producer/schema.py`): `event_id, device_id, event_ts, ingest_ts, co,
  humidity, lpg, smoke, temp, light, motion, pressure, is_synthetic`. No `is_anomaly` /
  `anomaly_reason` / `write_ts` / `bucket_start` — those are P3/Cassandra-sink-owned.
- `event_ts` / `ingest_ts` are **ISO-8601 UTC strings with millisecond precision**,
  e.g. `"2026-08-18T10:00:00.000Z"` — not epoch millis. Spark's `to_timestamp()` parses
  this natively; this was a deliberate choice specifically so P3 doesn't have to guess.
- Kafka message key = `device_id` (UTF-8 encoded) — matches FR-K1's partitioning intent.
- The producer runs **always-on** with plain `docker compose up -d` (no `profiles:`
  gating) — every stack restart re-starts ingestion from the beginning of the CSV unless
  `PRODUCER_REPLAY_ROW_LIMIT` is set. This was an explicit choice (see
  `docs/TROUBLESHOOTING.md` if this ever causes dev friction during P4/P5 work — the
  original plan considered gating it behind a compose profile and was overridden).
- Producer state is exposed at `GET http://localhost:${PRODUCER_STATE_PORT}/state`
  (default host port 8001) - read-only telemetry (FR-I4), not a control surface. There is
  still no start/stop control anywhere (CLI or UI) — Phase 1 stays observer-only per
  REQUIREMENTS.md §2; UC-7 (UI control panel) remains an explicitly later phase.
- Anomaly injection (synthetic mode only) can spike **multiple metrics per event**
  simultaneously (weighted 1/2/3 metrics: 70/25/5%), each offset by
  `PRODUCER_ANOMALY_SIGMA_MULTIPLIER` (default `4.0`, deliberately above §5.4's 3σ
  detection threshold to survive baseline drift between the producer's startup baseline
  and Spark's future rolling mean). **P3's rule-based anomaly detector should expect
  this** — a single anomalous event may show deviations on more than one metric at once.

## What P3 needs to do (from REQUIREMENTS.md §7 FR-S, §14)

Not started yet. When picking this up:
- FR-S1: PySpark Structured Streaming job consuming `sensor-readings` in micro-batches.
- FR-S2: 1-minute and 1-hour tumbling windows, per device and per metric — write into the
  already-existing `agg_1m` / `agg_1h` tables (schema above, first-cut column set may
  need adjusting once real aggregation logic is written — the CQL files say as much in
  their comments).
- FR-S3: rule-based anomaly flagging (§5.4: N=3σ from a device's rolling mean, or an
  absolute safety threshold) — this is where `is_anomaly` / `anomaly_reason` actually
  get populated on `raw_events`. Remember the producer can inject multi-metric
  anomalies; `anomaly_reason` should be able to reflect more than one triggering metric.
- FR-S4: streaming-query progress (batch id, input rows, processing time, watermark)
  exposed to Prometheus/web app — likely a P4 concern to actually wire up, but worth
  keeping in mind when structuring the job.
- Spark master/worker containers already exist and are healthy (P1) but have never had
  a job submitted to them — first real test of that part of the stack.
