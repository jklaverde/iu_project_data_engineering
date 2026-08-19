# Project Progress / Continuation Notes

Running status doc so a future session (or a different machine) can pick this project
back up without re-deriving context. Update this at the end of each phase. See
`REQUIREMENTS.md` for the frozen v1.0 spec and phase roadmap (§14) — this file tracks
progress *against* that roadmap plus implementation-level decisions the requirements
doc doesn't cover. See `docs/TROUBLESHOOTING.md` for bugs/gotchas found along the way.

---

## Status: P1-P5 done, committed. Interim single-VPS deployment done and live-validated on a real VPS. Full P6 (3-VPS k3s) and P7 (endurance) not started.

| Phase | What it is | Status |
|---|---|---|
| P1 — Foundation | docker-compose stack: Kafka, Cassandra, Spark (standalone, no job), Prometheus, Grafana | **Done** (commits `cab33ec`, `e0d4d25`) |
| P2 — Ingestion | Producer: Kaggle replay + synthetic hand-over | **Done** (commit `3d141b4`) |
| P3 — Processing | PySpark Structured Streaming job: validation, anomalies, dual windows, Cassandra sink | **Done** (see this file's P3 section) |
| P4 — Observability | Exporters wired, Grafana dashboards provisioned (KPI-1..5) | **Done** (see this file's P4 section) |
| P5 — Web app | FastAPI read-only API + React (TypeScript) guided UI + basic login | **Done** (see this file's P5 section) |
| Interim VPS deployment | Single-VPS Compose deployment: `dataset-init`, reboot-safe restart policies, `docs/ARCHITECTURE.md` + `docs/DEPLOYMENT.md`, a real Grafana dashboard bug found and fixed on a live deploy | **Done — actually deployed and used on a real Linux VPS**, not just designed (see this file's "Interim VPS deployment" section below) |
| P6 (full) — VPS deployment | 3 Contabo VPS, k3s, hardening, Kafka/Cassandra replicated across nodes | **Not started** — see "What full P6 (k3s) needs to know" below |
| P7 — Endurance | 48-hour run against §10 acceptance criteria | Not started |

**If you're picking this project back up, read "Where to pick this up next" at the very
bottom of this file first** — it's the prioritized list of what's actually worth doing
next, ahead of everything else in this file.

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

The Kaggle dataset (`iot_telemetry_data.csv`, gitignored, not committed) is fetched
automatically by the `dataset-init` one-shot service into a named volume
(`kaggle_dataset`) — no manual step needed, and it's a no-op on restarts once the
volume already has the file (see `docs/TROUBLESHOOTING.md` P6 section for the bug this
replaced: a bare VPS deploy used to crash-loop `producer` because that manual step was
easy to skip). To fetch it by hand instead (e.g. to inspect it outside Docker), run
`python kaggle_repository/download_repository.py`.

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
kaggle_repository/           P6: dataset-init's own Dockerfile + requirements.txt +
                             download_repository.py (also runnable standalone)
producer/                   P2: the ingestion service (own Dockerfile + requirements.txt)
  producer/                 the importable Python package
spark_job/                  P3: the streaming job (own Dockerfile + requirements.txt)
  spark_job/                the importable Python package (shipped to executors as a
                             zip via --py-files - see docs/TROUBLESHOOTING.md #7)
  worker.Dockerfile         spark-worker's own image build (needs the same Python deps
                             as the driver - see docs/TROUBLESHOOTING.md #6)
docs/
  ARCHITECTURE.md           every module explained, system + data-flow diagrams,
                             security model - the user-facing "how it's built" doc
  DEPLOYMENT.md             step-by-step single-VPS deployment guide (hardening,
                             firewall, optional TLS reverse proxy, backups) - this is
                             the guide actually used for the live VPS deploy below
  TROUBLESHOOTING.md        bugs/gotchas log, by phase
  PROGRESS.md                this file
REQUIREMENTS.md             frozen v1.0 spec - do not edit casually, see its own changelog header
development_notes/          gitignored, LOCAL ONLY (not in git, may not exist on a
                             fresh clone/different machine) - a developer-facing build
                             narrative (what was built in what order, why, bugs found)
                             if it exists on the machine you're on, read it for a
                             deeper first-hand account than this file provides
```
Note `spark-worker` (defined in P1, `docker-compose.yml`) now also `build:`s
from `spark_job/worker.Dockerfile` instead of pulling the plain upstream image — it
needs the same Python packages as the driver whenever a job uses pandas UDFs.

`backend/` (P5) follows the same per-service `Dockerfile` + `requirements.txt` +
`README.md` pattern as `producer/`/`spark_job/`, with one deviation: its build
`context:` in `docker-compose.yml` is the **repo root**, not `./backend`, because its
multi-stage Dockerfile also needs to `COPY frontend/...` from a sibling directory (one
combined container serves both the API and the built React app — see §4.1's "Web app
(API + frontend)" single line item). `frontend/` is a plain Vite/React/TypeScript
project, not run standalone in production.

All three Python services now use **hash-pinned lockfiles** (NFR-10.8): each has a
`requirements.in` (direct deps) and a generated `requirements.txt`
(`pip-compile --generate-hashes`, run inside a container matching that service's own
runtime base image — see `backend/README.md` for the exact command and why it must run
in-container, not on a dev machine, for correct wheel hashes). Dockerfiles install with
`--require-hashes`.

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
  pulling `apache/spark:3.5.9` directly, and mounts both the `kaggle_dataset` volume
  read-only (populated by `dataset-init` — see the P6 section below) and the checkpoint
  volume — required because executors run there, not in the
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

## P5 — Web app: implementation decisions and the state things are actually in now

- **One combined container.** `backend`'s Dockerfile is multi-stage: a `node:24-slim`
  stage builds the React app (`npm ci && npm run build`), then a
  `python:3.11.9-slim-bookworm` stage installs the hash-pinned Python deps and serves
  the built `dist/` via FastAPI's `StaticFiles` mounted at `/`, alongside the `/api/*`
  and `/ws/*` routes. Host port 8000 (`BACKEND_PORT`).
- **Auth**: a single admin credential (`BACKEND_ADMIN_USERNAME`/`BACKEND_ADMIN_PASSWORD`,
  both required env vars, no defaults — same "required, no fallback" pattern as
  `GRAFANA_ADMIN_PASSWORD`) plus a hand-rolled HMAC-SHA256-signed session cookie
  (`backend/app/auth.py`) — no session-management dependency, deliberately, since
  there's one static credential rather than a user table. `BACKEND_SESSION_SECRET`
  (required, no default) signs it. Every `/api/*` data route and the WebSocket
  handshake are guarded by `require_session` (checked **before** the WS `accept()`).
- **Live updates**: WebSocket (`/ws/pipeline-state`) is primary; the frontend
  (`frontend/src/state/usePipelineState.ts`) falls back to polling
  `GET /api/pipeline-state` every `BACKEND_POLL_INTERVAL_SECONDS` (default 2s) if the
  socket doesn't open within 3s or drops. The backend's own two background loops
  (`backend/app/state_poller.py`) poll producer/spark-job `/state`, Kafka, and
  Cassandra regardless of which transport reaches the browser — a fast loop (every
  `BACKEND_POLL_INTERVAL_SECONDS`) for ingestion/kafka/spark/cassandra/summary, and a
  slower one (`BACKEND_HEALTH_CHECK_INTERVAL_SECONDS`, default 5s) for the deployment
  health grid.
- **Upstream-outage resilience**: `state_poller.py` caches the last-known-good
  `producer`/`spark-job` `/state` response and merges fresh data on top of that cache
  rather than on top of `{}` — a transient restart of either service no longer changes
  the *shape* of what the frontend receives, only `ingestion.source_reachable`. This
  was added after a real crash was found live (see `docs/TROUBLESHOOTING.md` P5 #2) —
  **do not remove this caching** without re-verifying the frontend survives a
  `docker compose restart producer` mid-session.
- **Cassandra "recent rows" bucket selection is event-time-based, not wall-clock**:
  `cassandra_client.py`'s `recent_raw_events_sync` derives which `(device_id,
  bucket_start)` partitions to point-read from real timestamps sampled off Kafka
  (`kafka_client.KafkaReader.get_recent_events()`), not from `datetime.now()` — required
  because REPLAY-mode `event_ts` values are historical (2020 Kaggle dates), not current
  wall-clock time (see `docs/TROUBLESHOOTING.md` P5 #1). Any future change to how
  "recent" is determined must keep this in mind.
- **Backend also runs its own lightweight Kafka consumer**
  (`backend/app/kafka_client.py`'s `KafkaReader`) — manual partition assignment,
  `OFFSET_END` at startup, no consumer group commits — purely to sample recent raw
  event content (producer's `/state` has no event content, only counters) and to
  compute broker watermark offsets for the Kafka step's lag chart. This is a read-only
  observer client; it must never be mistaken for or merged with the real Spark
  consumer.
- **No Docker socket** is used for the deployment-status step (UC-1) — every service is
  probed over its own HTTP/TCP port instead (see `backend/README.md` / the P5 plan for
  the reasoning: `:ro` doesn't actually restrict Docker API access, and a future P6 k3s
  pod has no Docker socket to mount anyway).
- **`/api/control/*` is reserved, not implemented** — no `routers/control.py` exists.
  This is the seam UC-7's future control panel (pause/resume producer, trigger
  hand-over) will need; documented in `backend/README.md` so it isn't rediscovered.
- **Known, accepted limitation**: `/api/anomalies` can hit `READ_TOO_MANY_TOMBSTONES`
  under high data volume — shared with the pre-existing P4 Grafana panel it mirrors,
  not something P5 introduced. See `docs/TROUBLESHOOTING.md` P5 #3 before changing
  either query.

## Interim VPS deployment — implementation decisions and current state

Not the full `REQUIREMENTS.md` §4.1 target (3-VPS k3s — that's "full P6" below, not
started). This is a smaller, real piece of work: making the existing single-host
Compose stack actually deployable on a public VPS, and **it has genuinely been
deployed to and exercised on a real Linux VPS** (dataset fetch tested cold, Grafana
login reconfigured, a real dashboard bug found and fixed against the live instance) —
this is meaningfully more validated than "designed but never run."

- **`dataset-init`** (own directory `kaggle_repository/`, own `Dockerfile` +
  hash-pinned `requirements.txt`) — a one-shot service, same idiom as
  `kafka-topic-init`/`cassandra-schema-init`, that downloads the Kaggle dataset into a
  new named volume (`kaggle_dataset`) before `producer`/`spark-job`/`spark-worker`
  start. Replaces a manual host-side `pip install kagglehub` step that (a) was easy to
  forget entirely on a fresh VPS clone, crash-looping `producer`, and (b) fails outright
  on modern Debian/Ubuntu with a PEP 668 `externally-managed-environment` error even
  when remembered. **Confirmed needs no Kaggle credentials** for this dataset (it's
  public) — `KAGGLE_USERNAME`/`KAGGLE_KEY` in `.env` are an untested-but-present
  fallback only, not required. Idempotent: skips the download if the volume already has
  the file. `producer`/`spark-job`/`spark-worker` all switched from a
  `./kaggle_repository:/data:ro` host bind-mount to this named volume, and all three
  gained `depends_on: dataset-init: condition: service_completed_successfully`. Full
  story: `docs/TROUBLESHOOTING.md` P6 §1.
- **Every long-running service got `restart: unless-stopped`** (previously only
  `spark-job` had it) — without this, an unattended VPS reboot would leave most of the
  stack down until someone manually ran `docker compose up -d` again. Purely additive,
  doesn't change local-dev behavior.
- **`docs/ARCHITECTURE.md` and `docs/DEPLOYMENT.md` are new** — the user-facing
  "how it's built" and "how to put it on a VPS" docs (see their own content for what's
  in them; both are written to also be read by a newcomer, not just future-Claude).
  `README.md` was also rewritten — it had been stuck describing only P1 infrastructure.
- **A real bug was found and fixed against the live VPS deployment, not local dev**:
  four KPI-5 Grafana panels used bare `$granularity` in a table-name position
  (`FROM iot.$granularity WHERE ...`) instead of `${granularity}` like the working
  `device_id` variable in the same queries — Cassandra's CQL grammar treats a lone `$`
  as the start of a dollar-quoted string and fails parsing right after it. Fixed to
  `${granularity}` in `infra/grafana/provisioning/dashboards/json/kpi-dashboard.json`.
  Full root-cause story (including how it was diagnosed live via Grafana's Query
  Inspector and a direct `/api/ds/query` call against the running instance):
  `docs/TROUBLESHOOTING.md` P4 §14.
- **Important, non-obvious, NOT a bug**: KPI-5 panels can legitimately show "No data"
  for a long time after a fresh deploy, even with a perfectly correct query. Cassandra's
  `window_start` is derived from each row's own `event_ts`, which during REPLAY mode is
  a historical Kaggle-dataset date (e.g. `2020-07-15`) — confirmed by querying `agg_1m`
  directly on the live VPS. Since the panels filter `window_start` against Grafana's
  real wall-clock time range, **no row can ever match until the producer hands over to
  SYNTHETIC mode** (real timestamps). This is the same wall-clock-vs-event-time root
  cause as the P5 backend bug (`docs/TROUBLESHOOTING.md` P5 §1), just surfacing in
  Grafana instead. **Don't "fix" this again** — it resolves on its own, or force it
  sooner with `PRODUCER_REPLAY_ROW_LIMIT` for testing. Full story:
  `docs/TROUBLESHOOTING.md` P4 §14's "Related, NOT a bug" note.
- **The live VPS deployment's IP/credentials are intentionally not recorded anywhere in
  this repo** — if you need to reach it again, ask the user; don't assume a specific
  address or store one here even temporarily.

## What full P6 (k3s) needs to know (wire contract / deployment notes)

- The whole web app is **one container** (`backend`, built from repo-root context) —
  P6's k3s manifests need exactly one Deployment/Service for this, not two. No Docker
  socket dependency to worry about porting.
- `BACKEND_ADMIN_PASSWORD` and `BACKEND_SESSION_SECRET` are required env vars with no
  defaults, same pattern as `GRAFANA_ADMIN_PASSWORD` — P6's secrets management needs to
  supply both. `BACKEND_COOKIE_SECURE=false` is a **local-dev-only** setting; P6 (real
  TLS) must set it `true` or session cookies won't get the `Secure` flag in production.
- All three Python services' `requirements.txt` are hash-pinned and installed with
  `pip install --require-hashes` — if P6's deployment pipeline ever needs to bump a
  dependency, regenerate via the `pip-compile --generate-hashes` command in
  `backend/README.md` (run inside a container matching the target platform), don't
  hand-edit the lockfiles.

---

## Where to pick this up next

Read this section first if you're extending the project. Roughly in priority order —
not a strict queue, pick whichever matches what's actually being asked for:

1. **Full P6 (3-VPS k3s cluster)** — the actual next roadmap phase per
   `REQUIREMENTS.md` §4.1/§14. Not started; the interim single-VPS deployment above is
   real but is explicitly *not* this. Needs: k3s manifests (StatefulSets for
   Kafka/Cassandra, D19 — no operators), Traefik ingress + self-signed TLS (D25),
   flannel WireGuard inter-node traffic, NFR-11 firewall rules, NFR-12 node sizing. The
   "What full P6 (k3s) needs to know" section directly above has the wire-contract
   details (single web-app container, required secrets, hash-pinned deps) already
   confirmed and ready to carry over.
2. **P7 — 48-hour endurance run** (§10 acceptance criteria) — can actually be attempted
   against the *current* single-VPS or local deployment even before full P6 exists,
   since the acceptance criteria (sustained 500 msg/s, no restarts, bounded lag/disk
   growth) don't inherently require the multi-node topology. Worth checking with the
   user whether they want this run against what exists now or want to wait for full P6.
3. **UC-7 — web app control panel** (start/stop producer, trigger hand-over, from the
   UI) — explicitly deferred since Phase 1's inception. The backend already reserves
   `/api/control/*` (no `routers/control.py` yet — see the P5 section above) as the
   intended seam; the frontend has no control affordances at all yet. This is a
   self-contained, medium-sized feature addition, not a rethink of anything existing.
4. **Known technical debt, not yet fixed** (safe to leave, but don't rediscover from
   scratch if asked to address them):
   - `/api/anomalies` and its mirrored Grafana panel can hit
     `READ_TOO_MANY_TOMBSTONES` under sustained data volume (`docs/TROUBLESHOOTING.md`
     P5 §3) — likely needs a Spark-sink-level fix (write `unset` instead of `null` for
     optional Cassandra columns) or Cassandra compaction tuning, not a query change.
   - The frontend's production JS bundle is a single ~1.3 MB chunk (Vite's own build
     warning, not investigated further) — code-splitting (e.g. lazy-loading ECharts or
     per-step chunks) would help initial load time but wasn't judged worth the
     complexity for a 6-step internal tool during P5.
5. **Anything not listed here** — this file plus `docs/TROUBLESHOOTING.md` (bugs/root
   causes/fixes, by phase) should cover essentially every non-obvious decision and gotcha
   in the codebase; `docs/ARCHITECTURE.md` covers what every module does and why. If a
   question isn't answered by those three files, it's genuinely new ground — treat it
   with the same rigor as everything above (verify against the real running system,
   don't assume, surface real trade-offs to the user rather than silently deciding them).
