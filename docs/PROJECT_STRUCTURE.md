# Project Structure

Every tracked file in the repo, grouped by directory, with what it does. This is the
finest-grained companion to `docs/ARCHITECTURE.md` (which explains things at the
module/container level) — use that one to understand *how the system works*, use this
one to find *which file to open* for a given piece of behavior. See `docs/PROGRESS.md`
for *why* things are built the way they are, and `docs/TROUBLESHOOTING.md` for bugs
already found and fixed in a given file before you go looking for new ones.

---

## Root

| File | What it does |
|---|---|
| `README.md` | User-facing quick start: prerequisites, one-command start, walkthrough guide, endurance-run procedure. |
| `REQUIREMENTS.md` | The specification — scope, architecture, decision log, phase roadmap. Do not edit casually; see its own changelog header. |
| `docker-compose.yml` | The entire stack: every service, port mapping, volume, healthcheck, and dependency ordering. Start here to see how any two services actually connect. |
| `.env.example` | Every runtime config variable, documented inline, with safe placeholder values. `cp` this to `.env` and fill in real secrets. |
| `.gitignore` | Excludes `.env`, `__pycache__`, the Kaggle CSV, frontend build artifacts, and the local-only `development_notes/` and `.claude/`. |

## docs/

| File | What it does |
|---|---|
| `ARCHITECTURE.md` | Every module explained (what it is, why it exists, ports, dependencies), system + data-flow diagrams, the security model, supply-chain policy. |
| `DEPLOYMENT.md` | Step-by-step guide to deploying the stack on a single public VPS — hardening, firewall, optional TLS reverse proxy, backups, updates. |
| `PROGRESS.md` | Running status/continuation doc — what's done, implementation decisions beyond what `REQUIREMENTS.md` specifies, and "Where to pick this up next." Read this first when resuming work. |
| `TROUBLESHOOTING.md` | Every non-obvious bug found while building and operating the stack: symptom, root cause, how it was found, the fix — ordered by phase. |
| `PROJECT_STRUCTURE.md` | This file. |

## backend/ — P5 web app API (FastAPI; built together with `frontend/` into one container)

| File | What it does |
|---|---|
| `Dockerfile` | Multi-stage build: a Node stage builds `frontend/`, then a Python stage installs hash-pinned deps and serves the built React app via `StaticFiles` alongside the API. Build context is the **repo root**, not `./backend` — the only service that deviates from the per-service context convention, because it needs to `COPY frontend/...`. |
| `README.md` | Auth model, the reserved `/api/control/*` seam for UC-7, hash-pinning regeneration command. |
| `requirements.in` / `requirements.txt` | Direct deps / hash-locked lockfile (`pip-compile --generate-hashes`, generated inside a matching base-image container — see the README). |
| `app/__init__.py` | Empty package marker. |
| `app/main.py` | `create_app()`: builds the `Config`, the Kafka/Cassandra readers, the `StatePoller`, wires the lifespan (start/stop background loops), registers every router, mounts the built frontend at `/`. The actual entrypoint (`app = create_app()`). |
| `app/config.py` | `Config` dataclass + `load_config()` — every `BACKEND_*`/`KAFKA_*`/`CASSANDRA_*` env var the service reads, with the same "required env var, no silent default" pattern used for secrets project-wide. |
| `app/logging_setup.py` | JSON-line log formatter, identical pattern to `producer`/`spark_job`'s own. |
| `app/auth.py` | Hand-rolled HMAC-SHA256-signed session cookie: `create_session_token`/`verify_session_token`/`check_credentials`, and the `require_session` FastAPI dependency every protected route uses. |
| `app/kafka_client.py` | `KafkaReader` — a **read-only observer** Kafka consumer (manual partition assignment, `OFFSET_END` at startup, no consumer-group commits): samples recent raw event content and computes per-partition broker watermark offsets. Never to be confused with the real Spark consumer. |
| `app/cassandra_client.py` | `CassandraReader` — single-partition point reads for "recent rows" (bucket derived from real observed Kafka timestamps, not wall-clock — see `docs/TROUBLESHOOTING.md` P5 §1) and the `/api/anomalies` query (mirrors the Grafana anomaly panel's CQL shape). Also `device_metadata_sync`/`device_thresholds_sync` (small lookup tables), `latest_reading_sync` (one device's newest row), and `aggregates_sync` (agg_1m/agg_1h history) for the R1 sensors/environment role. |
| `app/environment.py` | Pure functions (no I/O) turning a device's latest reading + its Cassandra-persisted threshold stats into role-appropriate signals: `metric_status`/`device_status` (ok/warning/critical, reusing Spark's own anomaly thresholds), `metric_ranges` (per-metric actual value + normal band + ceiling, for the UI's gauge), `air_quality_score`, `comfort_index`, `chronic_exposure_ratio`, `trend_direction`, and `metric_windows`/`rollup_metric_windows` (D34 — project one metric out of agg_1m/agg_1h rows, or roll agg_1h up into day/week buckets, for the timeline charts). |
| `app/upstream_http.py` | Stdlib `urllib` helpers (wrapped in `asyncio.to_thread`) to poll `producer`'s and `spark-job`'s `/state`/`/healthz` endpoints and to do plain HTTP reachability probes for the deployment-status step. |
| `app/state_poller.py` | `StatePoller` — the two background asyncio loops (fast: ingestion/kafka/spark/cassandra/summary; slow: deployment health grid) that assemble the combined snapshot and broadcast it over WebSocket. Caches last-known-good upstream state so a transient outage doesn't change the response shape (see `docs/TROUBLESHOOTING.md` P5 §2). |
| `app/ws_manager.py` | `ConnectionManager` — tracks connected WebSocket clients, broadcasts the snapshot to all of them. |
| `app/routers/__init__.py` | Empty package marker. |
| `app/routers/auth.py` | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`. |
| `app/routers/steps.py` | `GET /api/pipeline-state` (full snapshot) and `GET /api/steps/{name}` (one step). |
| `app/routers/anomalies.py` | `GET /api/anomalies?device_id=&since_minutes=&limit=`. |
| `app/routers/sensors.py` | `GET /api/sensors` (every known device: metadata, latest reading, status, air quality score, comfort index, per-metric actual-vs-acceptable ranges — feeds the planner role's map), `GET /api/sensors/{device_id}/history` (chronic-exposure ratio + trend for the stat tiles), and `GET /api/sensors/{device_id}/timeline` (per-metric minute/hour/day/week points + an `unhealthy` flag per window, for the behavior-over-time charts). |
| `app/routers/admin.py` | `POST /api/admin/alerts/webhook` (unauthenticated — receives Grafana's alertmanager-style webhook payload, see `infra/grafana/provisioning/alerting/`) and `GET /api/admin/alerts` (admin-role-gated recent alert feed). Split into two `APIRouter`s so `main.py` can gate them differently. |
| `app/alert_store.py` | `AlertStore` — small in-memory ring buffer of recent Grafana-fired alerts; Grafana itself stays the system of record, this is just a live feed for the admin UI. |
| `app/routers/ws.py` | `/ws/pipeline-state` — validates the session cookie *before* accepting the WebSocket handshake, sends the cached snapshot immediately, then just waits for broadcasts. |

## frontend/ — P5 role-based UI (React + TypeScript + Vite + Apache ECharts + Leaflet)

| File | What it does |
|---|---|
| `package.json` / `package-lock.json` | Explicit, minimal, exact-pinned dependency list (NFR-10.1) + committed lockfile. |
| `.npmrc` | `ignore-scripts=true` (NFR-10.2). |
| `tsconfig.json` / `vite.config.ts` / `index.html` | TypeScript config; Vite config (dev-mode `/api`/`/ws` proxy to the backend container); the single HTML shell. |
| `README.md` | NFR-10.1 justifications for TypeScript and Leaflet (the two off-allowlist dependencies). |
| `src/main.tsx` | React root render (`createRoot(...).render(<App/>)`). |
| `src/App.tsx` | Top-level component: checks auth (`GET /api/auth/me`, now carries `role`), shows `LoginForm`, the admin `Shell` (stepper + pipeline diagram + the active step), or the planner `MapView`. |
| `src/api.ts` | `fetch`-based API client (credentials included), `connectPipelineStateSocket()` WebSocket helper, `fetchSensors`/`fetchSensorHistory` for the planner role. |
| `src/types.ts` | TypeScript interfaces mirroring every backend response shape — the single source of truth for the frontend/backend JSON contract. Includes `Role`, `SensorEntry`, `AggregateWindow`, etc. |
| `src/vite-env.d.ts` | Vite's ambient type declarations. |
| `src/styles.css` | All styling — dark theme, layout, the SVG pipeline-flow animation's keyframes, the planner map/status-badge styles. |
| `src/auth/LoginForm.tsx` | The login screen (shared by both roles; passes the returned `role` up to `App`). |
| `src/layout/Stepper.tsx` | The six-step side navigation (freely clickable, not gated). |
| `src/layout/StepShell.tsx` | Shared "waiting for data..." wrapper every step component uses. |
| `src/layout/ErrorBoundary.tsx` | Per-step React error boundary (added after a real crash — see `docs/TROUBLESHOOTING.md` P5 §2) so one step's bad data can't freeze the whole app. |
| `src/pipeline/PipelineFlowDiagram.tsx` | The custom SVG pipeline animation (D26) — 4 boxes, CSS motion-path particles, the REPLAY/SYNTHETIC hand-over badge. |
| `src/charts/EChartWrapper.tsx` | Reusable ECharts `init`/`setOption`/`dispose` wrapper used by every chart. |
| `src/state/usePipelineState.ts` | The WebSocket-primary/polling-fallback hook every admin step reads live data from. |
| `src/state/useSensors.ts` | Polling hook (`GET /api/sensors`) the planner map view reads live sensor data from. |
| `src/steps/DeploymentStep.tsx` | Step 1 — service health grid. |
| `src/steps/IngestionStep.tsx` | Step 2 — producer mode/counters/recent events. |
| `src/steps/KafkaStep.tsx` | Step 3 — live throughput chart + per-query lag. |
| `src/steps/SparkStep.tsx` | Step 4 — per-query batch progress + end-to-end latency. |
| `src/steps/CassandraStep.tsx` | Step 5 — most recently written rows. |
| `src/steps/SummaryStep.tsx` | Step 6 — totals + the Grafana link (built client-side from `location.hostname`). |
| `src/planner/MapView.tsx` | Environmental/planner role's top-level view (R2) — raw Leaflet map (no react-leaflet, to keep the dependency minimal) centered on Lingen (Ems), one status-colored marker per sensor from `useSensors()`. |
| `src/planner/SensorDetailPanel.tsx` | Selected sensor's readings, status badge, and stat tiles (air quality score, comfort index, chronic exposure/trend) with a `MetricGauge` per metric. |
| `src/planner/SensorTimeline.tsx` | Full-width behavior-over-time panel (D34) — a metric selector plus four charts (minute/hour/day/week, `GET /api/sensors/{id}/timeline`), each with a shaded `markArea` over any span where that metric was outside the acceptable range. |
| `src/planner/MetricGauge.tsx` | Actual-vs-acceptable range bar for one metric — current value, the normal band (mean ± 2σ, `backend/app/environment.py`'s `metric_ranges()`), and the hard ceiling for co/lpg/smoke, all on one scale. |
| `src/admin/AlertsTab.tsx` | Admin role's Alerts tab (R4) — polls `GET /api/admin/alerts`, each entry links out to a client-built Grafana Explore URL (Loki query pre-filled for that alert's service) for log drill-down. |

## producer/ — P2 ingestion service

| File | What it does |
|---|---|
| `Dockerfile` | `python:3.11.9-slim-bookworm`, hash-pinned install (`--require-hashes`). |
| `README.md` | Standalone-run instructions, the `PRODUCER_REPLAY_ROW_LIMIT` dev fast-forward knob, the `/state` endpoint contract. |
| `requirements.in` / `requirements.txt` | `confluent-kafka` direct dep / hash-locked lockfile. |
| `producer/__init__.py` | Empty package marker. |
| `producer/main.py` | Entrypoint: loads config, computes baseline stats, starts the state server, runs replay then synthetic generation. |
| `producer/config.py` | `Config` dataclass + `load_config()` for every `PRODUCER_*`/`KAFKA_*` env var. |
| `producer/schema.py` | `build_event()` — the single canonical JSON event shape every downstream consumer (Spark, the backend) depends on. |
| `producer/device_stats.py` | `compute_baseline_stats()` — one streaming pass over the CSV computing per-device mean/std/min/max via Welford's online algorithm (O(1) memory), plus per-hour temperature/light baselines used by synthetic generation. |
| `producer/replay.py` | `run_replay()` — streams the CSV top-to-bottom in file order (already globally time-sorted), publishing one event per row, then triggers hand-over. |
| `producer/synthetic.py` | `SyntheticGenerator`/`run_synthetic()` — samples events from the baseline forever after replay ends, including the weighted multi-metric anomaly injection logic. |
| `producer/rate_limiter.py` | `RateLimiter` — fixed-cadence pacing on the monotonic clock; resyncs instead of bursting if it falls behind. |
| `producer/kafka_client.py` | `KafkaEventPublisher` — thin wrapper around `confluent_kafka.Producer` (idempotent, `acks=all`). |
| `producer/state.py` | `ProducerState` — thread-safe counters (mode, events sent, anomalies, hand-over timestamp) shared between the publish loop and the HTTP server. |
| `producer/state_server.py` | `GET /state`, `GET /metrics`, `GET /healthz` — the stdlib `ThreadingHTTPServer`. |
| `producer/metrics.py` | Hand-formatted Prometheus text exposition (no `prometheus_client` dependency, by design). |
| `producer/logging_setup.py` | JSON-line log formatter. |

## spark_job/ — P3 stream processing service

| File | What it does |
|---|---|
| `Dockerfile` | The driver image: pre-warms the Ivy cache for the Kafka/Cassandra connector jars at build time, zips `spark_job/` for `--py-files` distribution to executors. |
| `worker.Dockerfile` | The executor image — needs the identical `pandas`/`pyarrow` install as the driver, since `applyInPandasWithState` actually executes on the worker. |
| `entrypoint.sh` | The `spark-submit` invocation (master URL, `--packages`, `--py-files`, Cassandra connection conf). |
| `run.py` | Thin top-level script (sibling of the `spark_job/` package) that just calls `spark_job.main.main()` — exists so `spark-submit` doesn't break the package's internal relative imports. |
| `README.md` | Architecture summary, the `run.py` rationale, the Ivy-cache-at-build-time rationale. |
| `requirements.in` / `requirements.txt` | `pandas`/`pyarrow` direct deps / hash-locked lockfile (PySpark itself ships in the base image, not pip-installed). |
| `spark_job/__init__.py` | Empty package marker. |
| `spark_job/main.py` | Entrypoint: builds the `SparkSession`, computes the seed baseline, starts all three streaming queries, blocks on `awaitAnyTermination()`. |
| `spark_job/config.py` | `Config` dataclass + `load_config()` for every `SPARK_JOB_*`/`KAFKA_*`/`CASSANDRA_*` env var. |
| `spark_job/schema.py` | `EVENT_SCHEMA` (matches the producer's JSON exactly) + `read_kafka()`/`parse_and_cast()`. |
| `spark_job/baseline.py` | `compute_seed_baseline()` — one-time batch read of the CSV computing per-device mean/std (the EWMA seed) and per-device absolute ceilings for `co`/`smoke`/`lpg`. |
| `spark_job/device_thresholds_sink.py` | `write_device_thresholds()` — persists that same seeded baseline into `iot.device_thresholds` once at startup, so the backend's environmental/planner role (`backend/app/environment.py`) reads the exact same numbers this job's own anomaly detector uses. |
| `spark_job/anomaly_state.py` | `flag_anomalies()` / the `applyInPandasWithState` function — the adaptive per-device EWMA anomaly detector, checked *before* the state updates with the current event's own value. |
| `spark_job/raw_query.py` | `build_raw_query()` — the `raw_events` streaming query (validates, detects anomalies, buckets, writes every row with `write_ts` + latency tracking). |
| `spark_job/agg_query.py` | `build_agg_query()` — the shared builder both `agg_1m` and `agg_1h` use (tumbling window, per-metric avg/min/max, anomaly/active-ratio aggregates). |
| `spark_job/cassandra_sink.py` | `make_foreach_batch_writer()` — the shared `foreachBatch` Cassandra writer; `stamp_write_ts` and `latency_tracker` are `raw_events`-only (the connector rejects unknown columns on `agg_1m`/`agg_1h` — see `docs/TROUBLESHOOTING.md` #8). |
| `spark_job/time_buckets.py` | `with_bucket_start()`/`with_day()`/`with_month()` — the partition-key-column helpers matching each Cassandra table's schema exactly. |
| `spark_job/query_progress.py` | `QueryProgressTracker` + the `StreamingQueryListener` that feeds it — Spark's own REST API doesn't expose Structured Streaming progress as JSON. |
| `spark_job/latency_tracker.py` | `LatencyTracker` — the latest-micro-batch KPI-2 latency snapshot (fed by `cassandra_sink.py`'s `raw_events` writer). |
| `spark_job/state_server.py` | `GET /state` (query progress + latency), `GET /metrics`, `GET /healthz`. |
| `spark_job/metrics.py` | Hand-formatted Prometheus text exposition. |
| `spark_job/logging_setup.py` | JSON-line log formatter. |

## kaggle_repository/ — dataset fetch (interim VPS deployment work)

| File | What it does |
|---|---|
| `Dockerfile` | The `dataset-init` one-shot container image — installs `kagglehub`, runs as root (sole writer to a fresh named volume). |
| `requirements.in` / `requirements.txt` | `kagglehub` direct dep / hash-locked lockfile. |
| `download_repository.py` | Idempotent dataset fetch — skips the download if the target CSV already exists; reads `KAGGLE_DATASET_OUTPUT_DIR` so the same script works both inside the container (writes to `/data`) and run by hand locally (writes to `./kaggle_repository`). No credentials needed for this public dataset; `KAGGLE_USERNAME`/`KAGGLE_KEY` are a fallback only. |

## infra/ — Cassandra, Grafana, Prometheus config and custom images

| File | What it does |
|---|---|
| `cassandra/Dockerfile` | Bakes the jmx_exporter javaagent into the Cassandra image (needs `curl`+`ca-certificates` added first — the base image has neither). |
| `cassandra/jmx-exporter/cassandra-jmx-exporter.yml` | The jmx_exporter config — fetched verbatim from its own official Cassandra example, not hand-written; re-diff against upstream before changing metric names. |
| `cassandra/schema/001_keyspace.cql` | Creates the `iot` keyspace (`SimpleStrategy`, RF=1 — local/single-VPS only). |
| `cassandra/schema/002_raw_events.cql` | The `raw_events` table — partitioned by `(device_id, bucket_start)`, a 15-minute bucket. |
| `cassandra/schema/003_agg_1m.cql` | The `agg_1m` table — partitioned by `(device_id, day)`. |
| `cassandra/schema/004_agg_1h.cql` | The `agg_1h` table — partitioned by `(device_id, month)`. |
| `cassandra/schema/005_device_metadata.cql` | The `device_metadata` table (name/area/lat/lon per known device) + its seed `INSERT`s — data-derived Lingen (Ems) placements, not arbitrary (see `REQUIREMENTS.md` D28's neighboring history). Feeds the planner role's map. |
| `cassandra/schema/006_device_thresholds.cql` | The `device_thresholds` table — empty until `spark_job` writes it at startup (`spark_job/spark_job/device_thresholds_sink.py`). |
| `grafana/Dockerfile` | Bakes the `hadesarchitect-cassandra-datasource` plugin into a path **outside** the `grafana_data` volume (installing into the default path would be silently shadowed by that pre-existing volume). |
| `grafana/provisioning/datasources/datasources.yaml` | Auto-provisions the Prometheus, Cassandra, and Loki datasources — no manual UI setup. Loki needs no plugin (built into core Grafana), unlike Cassandra. |
| `grafana/provisioning/dashboards/dashboards.yaml` | Points Grafana at the dashboard JSON directory, `updateIntervalSeconds: 30`, `allowUiUpdates: false`. |
| `grafana/provisioning/dashboards/json/kpi-dashboard.json` | The single 5-row KPI dashboard (KPI-1..5) — every panel's exact CQL/PromQL query lives here. See `docs/TROUBLESHOOTING.md` #13 and P4 §14 before touching any Cassandra panel's `target` string. |
| `prometheus/prometheus.yml` | The real exporter scrape jobs (kafka-exporter, cassandra:7070, node-exporter, producer, spark-job). Requires `docker compose restart prometheus` after editing — no hot reload. |
| `loki/loki-config.yml` | Single-binary Loki (filesystem storage, RF=1 — same local-dev posture as Cassandra's keyspace) — the infrastructure/admin role's centralized log store (R3). |
| `promtail/promtail-config.yml` | Tails every compose container's stdout via Docker service discovery (no per-service logging change needed — everything already emits JSON-line logs) and ships to Loki. Only `container`/`stream`/`level` become indexed labels; everything else stays queryable via LogQL `\| json`. |
| `grafana/provisioning/alerting/rules.yaml` | Provisioned-as-code alert rules (R4): Kafka consumer lag, Cassandra write latency, elevated ERROR log rate (Loki), service down — every query reuses metric names already tested in `kpi-dashboard.json`. |
| `grafana/provisioning/alerting/contactpoints.yaml` | One webhook contact point → `backend`'s `/api/admin/alerts/webhook`. |
| `grafana/provisioning/alerting/policies.yaml` | Root notification policy routing every alert to that contact point. |
