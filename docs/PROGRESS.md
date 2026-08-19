# Project Progress / Continuation Notes

Running status doc so a future session (or a different machine) can pick this project
back up without re-deriving context. Update this at the end of each phase. See
`REQUIREMENTS.md` for the frozen v1.0 spec and phase roadmap (§14) — this file tracks
progress *against* that roadmap plus implementation-level decisions the requirements
doc doesn't cover. See `docs/TROUBLESHOOTING.md` for bugs/gotchas found along the way.

---

## Status: P1-P4 done, committed. P5 (Web app) is next.

| Phase | What it is | Status |
|---|---|---|
| P1 — Foundation | docker-compose stack: Kafka, Cassandra, Spark (standalone, no job), Prometheus, Grafana | **Done** (commits `cab33ec`, `e0d4d25`) |
| P2 — Ingestion | Producer: Kaggle replay + synthetic hand-over | **Done** (commit `3d141b4`) |
| P3 — Processing | PySpark Structured Streaming job: validation, anomalies, dual windows, Cassandra sink | **Done** (see this file's P3 section) |
| P4 — Observability | Exporters wired, Grafana dashboards provisioned (KPI-1..5) | **Done** (see this file's P4 section) |
| P5 — Web app | FastAPI read-only API + React guided UI + basic login | Not started |
| P6 — VPS deployment | 3 Contabo VPS, k3s, hardening | Not started |
| P7 — Endurance | 48-hour run against §10 acceptance criteria | Not started |

## Resuming locally

```
docker compose up -d
```
Brings up the full stack (Kafka + kafka-exporter, Cassandra with a baked-in JMX
exporter javaagent, Spark standalone + the streaming job, Prometheus, Grafana with the
Cassandra datasource plugin baked in, node-exporter, kafka-ui, and the producer) — the
producer starts automatically and immediately begins replaying the Kaggle dataset at
100 msg/s into topic `sensor-readings`, and the Spark job starts consuming and writing
to Cassandra immediately after. Grafana auto-provisions both datasources (Prometheus +
Cassandra) and one dashboard (5 rows, one per KPI-1..5) with zero manual UI steps. See
the root `README.md` for the verification checklist and `docker compose down` / `down -v`.

**If you edit `infra/prometheus/prometheus.yml` while the stack is already running,
`docker compose restart prometheus` is required** — Prometheus does not hot-reload
scrape config changes from a running container picking up an edited mounted file.

**Heads up on cold start:** on first launch (or after a full `down -v`), the Spark job
recomputes its anomaly-detection baseline from the CSV (~30-60s) before it starts
consuming, and if Kafka already has a large backlog (e.g. from a producer that's been
running a while), the first micro-batch can take several minutes to catch up — this is
expected, not a hang (see `docs/TROUBLESHOOTING.md` P3 section).

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
  cassandra/Dockerfile      P4: bakes in the jmx_exporter javaagent (KPI-4)
  cassandra/jmx-exporter/   P4: exporter config, based verbatim on jmx_exporter's own
                             official Cassandra example - see docs/TROUBLESHOOTING.md #12
                             before changing metric names in here
  grafana/Dockerfile        P4: bakes in the Cassandra datasource plugin
  grafana/provisioning/     P4: datasources.yaml (Prometheus + Cassandra) + one
                             dashboard JSON (5 rows, KPI-1..5)
  prometheus/prometheus.yml real exporter scrape jobs as of P4 (was self-scrape only)
producer/                   P2: the ingestion service (own Dockerfile + requirements.txt)
  producer/                 the importable Python package
spark_job/                  P3: the streaming job (own Dockerfile + requirements.txt)
  spark_job/                the importable Python package (shipped to executors as a
                             zip via --py-files - see docs/TROUBLESHOOTING.md #7)
  worker.Dockerfile         spark-worker's own image build (needs the same Python deps
                             as the driver - see docs/TROUBLESHOOTING.md #6)
docs/
  TROUBLESHOOTING.md        bugs/gotchas log, by phase
  PROGRESS.md                this file
REQUIREMENTS.md             frozen v1.0 spec - do not edit casually, see its own changelog header
```
Each future Python service (the P5 FastAPI backend) is expected to get its own
directory with its own `requirements.txt`, following the `producer/`/`spark_job/`
pattern — not a shared root dependency file (NFR-10.8's minimal-deps-per-service
spirit). Note `spark-worker` (defined in P1, `docker-compose.yml`) now also `build:`s
from `spark_job/worker.Dockerfile` instead of pulling the plain upstream image — it
needs the same Python packages as the driver whenever a job uses pandas UDFs.

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
  `is_anomaly`, `anomaly_reason` are populated by the P3 Spark job (done — see below).
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

**Spark job (P3) — implementation decisions and the state Cassandra is actually in now**
- Anomaly detection uses an **adaptive EWMA** per (device, metric) — not a static
  one-time baseline — seeded from a one-time batch read of the CSV at job startup, then
  continuously updated per event (decay `SPARK_JOB_ANOMALY_EWMA_ALPHA`, default
  `0.001`, ≈2000-event/12-60s effective window). This was a deliberate choice over a
  simpler static baseline (the user explicitly picked "adaptive" when asked). Checked
  **before** updating with the current event's own value, so an event never biases the
  baseline it's being tested against.
- Separately, a **static per-device absolute ceiling** exists for `co`/`smoke`/`lpg`
  only (`max(observed_max, p999) × 1.5`, computed once from the CSV) — `temp`/`humidity`
  rely on the sigma rule alone, no ceiling concept.
- `anomaly_reason` is a semicolon-joined `metric:kind(detail)` string, e.g.
  `"co:sigma(3.75sigma);lpg:sigma(3.70sigma);smoke:sigma(3.71sigma)"` — can and does
  reflect multiple simultaneously-triggering metrics on one event (matches the
  producer's multi-metric injection). Confirmed working for both real historical-data
  outliers during replay (anomaly detection is NOT synthetic-only) and injected
  synthetic anomalies.
- Three fully independent Structured Streaming queries (`raw_events`, `agg_1m`,
  `agg_1h`), each with its own Kafka read and own checkpoint under
  `/opt/spark-checkpoints/<name>` (named volume `spark_checkpoints`, mounted on **both**
  `spark-job` and `spark-worker` — state-store data is written by executors, see
  `docs/TROUBLESHOOTING.md` #5).
- `write_ts` exists only on `raw_events` (stamped by the Cassandra sink at write time,
  feeds KPI-2) — do not add it to writes for `agg_1m`/`agg_1h`, their CQL schemas don't
  have that column (`docs/TROUBLESHOOTING.md` #8).
- FR-S4 (query progress exposed to a backend): same pattern as the producer — a
  built-in stdlib HTTP `/state` endpoint (`GET http://localhost:${SPARK_JOB_STATE_PORT}/state`,
  default host port 8002), fed by a custom `StreamingQueryListener` (Spark's own REST
  API on port 4040 does not expose Structured Streaming query progress, confirmed not
  assumed). `GET /healthz` for the compose healthcheck.
- `spark-worker` now builds a custom image (`spark_job/worker.Dockerfile`) instead of
  pulling `apache/spark:3.5.9` directly, and mounts both `./kaggle_repository:/data:ro`
  and the checkpoint volume — required because executors run there, not in the
  `spark-job` driver container (see `docs/TROUBLESHOOTING.md`'s whole P3 section, which
  is entirely about this driver/executor distinction).

**Observability (P4) — implementation decisions and the wire contract for P5**
- Producer and Spark job both gained `GET /metrics` (Prometheus text exposition,
  hand-formatted, no `prometheus_client` dependency) alongside their existing `/state`
  JSON — same port (8000 internal), same HTTP server. P5's backend can read either
  `/state` (JSON, simpler to consume) or scrape `/metrics` itself if it wants
  Prometheus-native data; both stay in sync since they read the same tracker objects.
- **KPI-1 lag is genuinely 3 separate numbers**, not one — the `raw_events`/`agg_1m`/
  `agg_1h` queries are 3 independent Kafka consumers (Structured Streaming doesn't use
  classic consumer-group offsets, so `kafka_consumergroup_lag` isn't usable here; lag
  is computed in PromQL as broker offset (`kafka_topic_partition_current_offset`,
  from kafka-exporter) minus Spark's self-reported offset
  (`spark_job_kafka_consumed_offset{query,partition}`, added to
  `query_progress.py`'s listener in P4) — legend/label by `query`, don't collapse to a
  single number.
- **KPI-2 latency is a per-micro-batch snapshot** (p50/p95/max of `write_ts -
  event_ts`, plus a produce→ingest and ingest→write hop breakdown), computed in
  `cassandra_sink.py`'s `raw_events` writer only (the only table with all 3
  timestamps on one row) and exposed via a new `LatencyTracker`. Not a true
  cross-batch streaming quantile — refreshed every trigger interval (30s default),
  which is what actually matters for checking NFR-1's bound is currently met.
- **Grafana needs two datasources** — Prometheus (KPI-1/2/4) and a baked-in Cassandra
  plugin, `hadesarchitect-cassandra-datasource` (KPI-3/5, queried directly against
  `agg_1m`/`agg_1h`/`raw_events`). The plugin is baked into a custom `grafana`
  image at a path **outside** the pre-existing `grafana_data` named volume
  (`GF_PATHS_PLUGINS=/usr/local/grafana-plugins`) — installing into the default
  `/var/lib/grafana/plugins` would be silently shadowed by that already-populated
  volume forever. If a future phase adds more plugins, keep using this same
  out-of-volume path.
- **Cassandra now builds a custom image too** (`infra/cassandra/Dockerfile`), baking
  in a jmx_exporter javaagent via `JVM_EXTRA_OPTS` (port 7070). The exporter config
  (`infra/cassandra/jmx-exporter/cassandra-jmx-exporter.yml`) is jmx_exporter's own
  official Cassandra example fetched verbatim, not hand-written — if KPI-4 metrics
  ever need to change, re-diff against the upstream example rather than guessing at
  MBean names; real metric names sometimes differ from what seems obvious (e.g. disk
  usage is `cassandra_storage_load_count`, not `..._load`, and GC pauses come from
  jmx_exporter's own built-in JVM collector as `jvm_gc_collection_seconds_{count,sum}`,
  not a custom rule — see `docs/TROUBLESHOOTING.md` #12).
- The dashboard's `$device_id` template variable is a **static list** (the 3 real
  device MAC IDs), not a CQL-driven variable — `SELECT DISTINCT` isn't valid on a
  partial partition-key column in Cassandra. If a future phase ever adds real devices
  beyond these 3 (it currently never does — confirmed the synthetic generator only
  ever cycles the same 3 IDs), this variable needs a matching update.
- `docker compose restart prometheus` is required after editing
  `infra/prometheus/prometheus.yml` on an already-running stack — no hot reload.

## What P5 needs to do (from REQUIREMENTS.md §7 FR-W, §14)

Not started yet. When picking this up:
- FastAPI read-only API (FR-W2: observer mode only, Phase 1 has no control-panel
  endpoints — see UC-7, explicitly a later phase) + a React guided UI + basic login
  (FR-W4).
- The producer's and Spark job's `GET /state` (JSON) endpoints are exactly what this
  backend should poll for live pipeline state — internal ports `producer:8000` /
  `spark-job:8000` from inside the Docker network, or the host-mapped
  `PRODUCER_STATE_PORT`/`SPARK_JOB_STATE_PORT` (8001/8002) if developing the backend
  outside Compose.
- FR-W1's guided steps (deployment status → ingestion → Kafka → Spark → Cassandra →
  KPI summary linking to Grafana) map directly onto what already exists: producer
  `/state` for ingestion, Kafka broker/kafka-exporter for the Kafka step, Spark job
  `/state` for the Spark step, and a Cassandra read (or the same `/state` data) for
  the storage step.
- FR-W3 (live updates, WebSocket or ≤2s polling): both `/state` endpoints are cheap
  in-memory reads, safe to poll frequently from a backend.
