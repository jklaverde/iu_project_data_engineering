# Streaming Sensor Pipeline — Requirements Document (v2.0)

**Project:** Role-based environmental sensor platform for the municipality of Lingen (Ems) — an
infrastructure/admin role (pipeline health, centralized logs, alerting) and an environmental/planner
role (live sensor map, air quality/comfort scoring, citizen-facing warnings), both served from the
same streaming pipeline and KPI dashboard.
**Status:** **v2.0 — approved for development.** v1.0's technical pipeline (Kafka/Spark/Cassandra) is
unchanged; v2.0 redirects the *purpose* the two user-facing surfaces serve — see the v2.0 changelog
entry below and D29-D33.
**Date:** 2026-08-14 (v1.0), 2026-08-21 (v2.0)
**v0.2 changes:** frontend (React.js) and backend (Python) confirmed; added NFR-10 npm supply-chain security policy and Risk R-5, based on the 2025–2026 npm attack landscape (Shai-Hulud worm and successors, axios and keyv compromises).
**v0.3 changes:** deployment target defined — two Contabo VPS orchestrated with Docker Swarm, true-cluster topology (Kafka broker + Cassandra node on both machines, replication factor 2), public exposure via IP address; added §4.1 deployment topology, NFR-11/NFR-12, Risk R-6, OQ-6/OQ-7.
**v0.4 changes:** orchestrator switched from Docker Swarm to **k3s** on **three** Contabo VPS (2 data nodes + 1 small control node; HA control plane with 3-member etcd; 3 KRaft controllers), Kafka/Cassandra as plain StatefulSets; OQ-7 resolved; OQ-4 resolved as KRaft; D16 superseded by D18/D19; NFR-11/NFR-12 and phases updated.
**v1.0 changes:** all remaining open questions closed — FastAPI confirmed (D21); all proposed numeric values accepted (D22); atmospheric pressure simulated for all rows, labeled synthetic (D23); raw events + aggregates in Cassandra confirmed (D24); TLS via self-signed certificate (D25); charting with Apache ECharts (D26); supply-chain scanning with Socket + free Socket Firewall + Trivy (D27).
**v2.0 changes:** reviewing the actual assignment brief (`development_notes/Assignments_Portfolio_DLBDSEDE02.pdf`) surfaced a drift — the system had become a pipeline-mechanics demo, when the brief's real scenario is a municipality using sensor data to inform planners and warn citizens. Redirected around two roles instead of one guided tour: **infrastructure/admin** (D28 replay-timestamp fix so "last N minutes" queries work from the start of a run; D29 role-based auth; D30 Loki + Promtail centralized logs; D31 Grafana alerting with a webhook into the backend and Explore drill-down links) and **environmental/planner** (D32 a Leaflet map of Lingen (Ems) with data-derived, not arbitrary, sensor placement; D33 threshold/AQI logic that reuses Spark's own baseline statistics rather than inventing separate numbers). §1, §2, §6, §7, and §9 updated accordingly; §3-5 and §10-14 extended, not replaced.

---

## 1. Purpose and Goals

The scenario (from the course's own assignment brief): a municipality — here, **Lingen (Ems),
Germany** — has installed environmental sensors around the city measuring temperature, humidity,
CO, LPG, and smoke. The goal is not to watch the pipeline move data around; it is to (1) give
**city planners** better information to improve environmental conditions over time, and (2) power
an application that **warns citizens** when a reading exceeds a recommended value. Both are
downstream consumers of the same real, locally deployable streaming pipeline: ingest via Apache
Kafka, process with Apache Spark, store in Apache Cassandra.

Two roles, two user-facing surfaces, both served by the same backend and pipeline:

1. **Environmental/planner role** — a live map of Lingen (Ems) with each sensor placed at a
   location its own data justifies (§5.6), colored by current status, showing an air quality
   score, a comfort index, chronic-exposure/trend metrics, and a citizen-facing recent-alerts
   feed. This is the surface that actually answers the brief's two questions.
2. **Infrastructure/admin role** — the original guided pipeline tour (deployment → ingestion →
   brokering → processing → storage) plus a realistic ops layer on top: centralized structured
   logs across every service (Loki), Grafana-fired alerts pushed live into the UI, and one-click
   drill-down from an alert into the exact logs that explain it. This role's job is to keep the
   planner/citizen-facing numbers trustworthy — a warning feed that silently goes stale is worse
   than no feed at all.
3. A **Grafana instance** exposing operational KPIs (pipeline health) and business KPIs (the same
   environmental data the planner role serves, for historical/cross-referencing use).

The system still doubles as an **endurance-test bench**: it must sustain a continuous data load
for approximately 2 days without Cassandra failing, while making the stress observable (disk
growth, write latency, consumer lag) — this is what makes the planner/citizen-facing numbers
something an admin can actually keep trustworthy over time, not just a one-off demo.

The primary goal is now twofold: a planner or citizen using the map should be able to answer "is
this location's air currently safe, and is it a persistent problem or a one-off," and an admin
using the infrastructure role should be able to tell, within one click from a live alert, what
broke and why.

---

## 2. Scope

### In scope (Phase 1)
- Real pipeline: actual Kafka, Spark, and Cassandra containers processing actual messages.
- Local development environment via Docker Compose on a single machine.
- **Production deployment on three Contabo VPS orchestrated with k3s** (lightweight
  Kubernetes): two data nodes each run one Kafka broker, one Cassandra node
  (replication factor 2), and one Spark worker; a third, smaller control node completes
  the HA control plane (3-member etcd) and the Kafka KRaft controller quorum, and hosts
  the web app, ingress, and monitoring — so distribution, replication, and node-failure
  behavior are genuinely observable.
- Data ingestion in two sequential modes: replay of a Kaggle dataset, then automatic
  hand-over to a synthetic generator that mimics the same schema.
- Spark Structured Streaming job computing windowed aggregates (1-minute and 1-hour).
- Cassandra as the time-series store; all data retained (no TTL).
- Web application in **observer mode**: read-only, live visualization of each stage.
- **Role-based access (D29):** two fixed accounts (infrastructure/admin, environmental/planner),
  session carries a role claim, each role lands on its own surface after login.
- **Environmental/planner role:** a Leaflet map of Lingen (Ems) (D32), one pin per sensor at a
  data-derived location (§5.6), live status/AQI/comfort-index/trend per sensor, a citizen-facing
  recent-alerts feed.
- **Infrastructure/admin role:** the original guided pipeline tour, plus centralized logs (Loki +
  Promtail, D30) and Grafana-fired alerts pushed into the UI with log drill-down (D31).
- Grafana dashboards for the KPI catalogue of §9 (now six families, not five).
- Basic login on the web application (now role-aware); Grafana's built-in authentication.
- 48-hour endurance-run scenario, with acceptance criteria (§10).

### Out of scope (Phase 1 — planned for later phases)
- Web-app **control panel** (start/stop flows, trigger bursts, inject anomalies from the UI).
  The backend API must be designed so these actions can be added without redesign.
- Kubernetes operators (Strimzi, K8ssandra): Phase 1 uses plain hand-written
  StatefulSets (D19); operators are a possible later phase.
- Docker Swarm: evaluated and superseded by k3s (D16 → D18).
- Real external device feeds (MQTT, field hardware).
- Machine-learning-based anomaly detection (Phase 1 uses rule-based detection only).
- Multi-tenant access or per-user accounts beyond the two fixed role-based logins (D29) — no user
  store, no self-service signup, no more than one admin identity and one planner identity.
- Custom domain name and DNS (exposure is via public IP addresses — see NFR-11 and OQ-6).

---

## 3. Tool Stack

| Layer | Tool | Notes / rationale |
|---|---|---|
| Containerization | Docker / containerd + Docker Compose | Compose for local development; the same container images run in the k3s cluster. |
| Orchestration | k3s (3 nodes, HA embedded etcd) | Lightweight Kubernetes; Kafka and Cassandra as plain StatefulSets with node-pinned local persistent volumes; flannel WireGuard backend encrypts all inter-node traffic. |
| Edge / TLS | Traefik ingress (bundled with k3s) + host firewall (ufw/nftables) | Only ingress ports are publicly reachable; everything else is cluster-internal, enforced additionally by NetworkPolicies. |
| Message broker | Apache Kafka (+ KRaft or ZooKeeper) | Topic `sensor-readings`; partitioned by device ID to preserve per-device ordering. |
| Stream processing | Apache Spark 3.x — Structured Streaming, **PySpark** | Python chosen for the whole codebase; micro-batch reads from Kafka, windowed aggregation, writes to Cassandra. |
| Storage | Apache Cassandra 4.x | Time-series data model; chosen for write-heavy, time-ordered sensor workloads. |
| Ingestion service | Python producer (kafka-python or confluent-kafka) | Replays Kaggle CSV at configurable rate, then switches to synthetic generation. |
| Web app — backend | Python (FastAPI) — confirmed (D21) | Read-only API exposing live pipeline state (Kafka offsets/lag, Spark batch stats, Cassandra rows) to the frontend; designed to accept control endpoints later. |
| Web app — frontend | React (JavaScript/TypeScript) + Apache ECharts (D26) + Leaflet (D32) | Role-based UI: the admin role keeps the step-by-step guided tour with animated in-app charts (ECharts) and the custom React/SVG pipeline-flow animation; the planner role adds a raw-Leaflet map (no react-leaflet, to keep the dependency minimal) of Lingen (Ems). WebSocket or polling for live updates. |
| KPI dashboards | Grafana | Reads from Prometheus (operational metrics), Cassandra (business aggregates), and Loki (logs, D30) — plus provisioned alert rules (D31) with a webhook contact point into the backend. |
| Metrics collection | Prometheus + exporters (Kafka exporter, Cassandra/JMX exporter, node exporter) | Required so Grafana can chart lag, disk growth, write latency; the pipeline itself does not need Prometheus to function. |
| Log aggregation | Grafana Loki + Promtail (D30) | Promtail tails every compose container's stdout via Docker service discovery — no per-service logging change needed, every service already emits JSON-line logs (§5.2-adjacent convention). Only `container`/`stream`/`level` are indexed labels; everything else stays queryable via LogQL. |
| Supply-chain security | Socket (GitHub App + CI CLI) + free Socket Firewall on dev machines + Trivy (containers, k3s manifests) + npm audit / pip-audit | Behavioral zero-day malicious-package detection (Socket), image/IaC scanning (Trivy), known-CVE checks (built-in auditors). See NFR-10. |
| Language | Python everywhere (except React frontend) | One language for producer, Spark job, and API: fastest to read, modify, iterate. |

---

## 4. Architecture and Workflow

```
             ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
 Kaggle CSV →│  Producer  │──▶│   Kafka    │──▶│   Spark    │──▶│ Cassandra  │
 then        │  (Python)  │   │ topic:     │   │ Structured │   │ keyspace:  │
 synthetic → │            │   │ sensor-    │   │ Streaming  │   │ iot        │
             └────────────┘   │ readings   │   └─────┬──────┘   └─────┬──────┘
                              └────────────┘         │                │
                    ┌────────────────────────────────┴────────────────┤
                    │              read-only state / metrics          │
             ┌──────▼──────┐                                   ┌──────▼──────┐
             │  Web app    │                                   │   Grafana   │
             │ (FastAPI +  │                                   │ (Prometheus │
             │  React)     │                                   │ + Cassandra)│
             └─────────────┘                                   └─────────────┘
```

**Data path (happy flow):**
1. The producer reads the Kaggle dataset and publishes JSON events to Kafka at a
   configurable rate. When the dataset is exhausted, it switches automatically and
   seamlessly to synthetic generation with the identical schema (§5.3).
2. Kafka distributes events across partitions keyed by device ID.
3. Spark consumes in micro-batches, validates/enriches events, detects rule-based
   anomalies, computes 1-minute and 1-hour windowed aggregates per device and per metric.
4. Spark writes both raw events and aggregates to Cassandra (see §7 FR-C).
5. The web app backend reads live state from Kafka (offsets, lag), Spark (batch/query
   progress), and Cassandra (latest rows) and streams it to the frontend.
6. Prometheus scrapes exporters; Grafana renders operational KPIs from Prometheus and
   business KPIs from Cassandra; Promtail ships every container's logs to Loki, which
   Grafana also reads for both ad-hoc log search (Explore) and alert evaluation (§4.2).
7. The same backend also serves the planner role directly from Cassandra: latest reading
   + device_thresholds → per-metric status, air quality score, comfort index (§5.6),
   independent of Grafana.

### 4.1 Deployment topology (three Contabo VPS, k3s)

```
        PUBLIC INTERNET ──── only ingress ports open (firewall on all nodes)
                 │
  ┌──────────────┴──────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
  │ VPS-3  control node (small) │ │ VPS-1  data node        │ │ VPS-2  data node        │
  │ ─ k3s server (etcd 1/3)     │ │ ─ k3s server (etcd 2/3) │ │ ─ k3s server (etcd 3/3) │
  │ ─ Traefik ingress + TLS     │ │ ─ Kafka broker 1        │ │ ─ Kafka broker 2        │
  │ ─ Kafka KRaft controller 3  │ │ ─ KRaft controller 1    │ │ ─ KRaft controller 2    │
  │ ─ Web app (API + frontend)  │ │ ─ Cassandra node 1      │ │ ─ Cassandra node 2      │
  │ ─ Producer                  │ │ ─ Spark worker 1        │ │ ─ Spark worker 2        │
  │ ─ Prometheus + Grafana      │ │                         │ │                         │
  │ ─ Loki + Promtail (D30)     │ │                         │ │                         │
  │ ─ Spark master              │ │                         │ │                         │
  └─────────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘
            all inter-node traffic over flannel WireGuard backend (encrypted)
```

- **Control plane (HA):** all three VPS run the k3s server role with embedded etcd
  (3-member quorum), so the Kubernetes control plane survives the loss of any single
  node — the coordination problem of the earlier two-node design is solved.
- **Kafka:** 2 brokers on the data nodes, topic replication factor 2; 3 KRaft
  controllers (one per node, the third on the control node) give the metadata quorum
  tolerance of one node loss. The web app shows partition leaders and replicas per node.
- **Cassandra:** 2-node cluster on the data nodes, keyspace replication factor 2; each
  data node holds a full copy of the data (disk sizing per data node — NFR-12).
  Honesty note: with RF=2, QUORUM (=2) reads/writes cannot tolerate a data-node loss;
  node-failure demonstrations therefore use consistency level ONE, and the walkthrough
  explains why — the control plane and Kafka metadata survive any single-node loss,
  while Cassandra QUORUM availability would require a third data replica (possible
  future upgrade: RF=3 with a Cassandra node added to VPS-3, at the cost of full-dataset
  disk there too).
- **Spark:** master (lightweight) on the control node; one worker per data node —
  processing work is visibly split across both data machines.
- **Workload style:** Kafka and Cassandra run as plain, hand-written **StatefulSets**
  with node-pinned local persistent volumes — no operators in Phase 1 (D19). Every
  manifest is transparent and explainable in the walkthrough; operators (Strimzi,
  K8ssandra) are a possible later phase.
- **Ingress:** k3s's bundled Traefik terminates TLS and routes to the web app and
  Grafana; nothing else is publicly reachable.
- **Local development** remains single-machine Docker Compose with one broker/one
  Cassandra node; the k3s manifests are the production deployment contract.

### 4.2 Role-based web app surfaces and alert flow

Both roles authenticate against the same FastAPI backend with a single shared login form; the
session token carries a `role` claim (`"admin"` or `"planner"`, D29) resolved from one of two fixed
credential pairs — there is no user store, no self-service accounts (§2 out-of-scope). The frontend
branches immediately after login with no client-side router: the planner role renders the Leaflet map
(D32); the admin role renders the original guided pipeline tour plus a new Alerts tab.

Alert flow (D31): Grafana evaluates its provisioned rules (§9's KPI-1/KPI-4 metrics plus a Loki-based
elevated-error-rate query) on its own schedule, and a firing/resolved alert is pushed via a webhook
contact point to `POST /api/admin/alerts/webhook` on the backend. The backend keeps a small in-memory
recent-alert buffer (not a durable log — Grafana remains the system of record) and broadcasts the
update over the existing pipeline-state WebSocket channel. The admin UI's Alerts tab polls the
backend's alert list and renders, for each alert, a link to a Grafana Explore URL built client-side
with a Loki query pre-filled for that alert's service and a recent time window — one click from "here
is a problem" to "here are the exact log lines that explain it."

---

## 5. Data Specification

### 5.1 Source dataset (replay phase)
- **Dataset:** Kaggle — `garystafford/environmental-sensor-data-132k`
  ("Environmental Sensor Telemetry Data").
- ~405,000 readings collected over 7 days from 3 IoT devices.
- Fields: timestamp (`ts`), `device` (identifier), `co` (carbon monoxide), `humidity`,
  `lpg`, `smoke`, `temp` (temperature), `light` (boolean), `motion` (boolean).
- The replay preserves the original inter-event ordering per device (the source file is
  already globally sorted, interleaved across devices, so reading it in file order alone
  is sufficient). The replay **rate** is configurable and independent of original
  timestamps, and so is `event_ts` itself: both replayed and synthetic events are stamped
  with the current time at production (`event_ts = ingest_ts = now()`), not the dataset's
  original 2020 timestamps (D28) — otherwise every "last N minutes" query would return
  nothing throughout the entire replay phase, since the source dataset predates any live
  run by years.
- Default replay rate: 100 messages/second (confirmed).

### 5.2 Canonical event schema
Every message on the topic — replayed or synthetic — follows one JSON schema containing at
minimum: `event_id`, `device_id`, `event_ts`, `ingest_ts`, the seven metric fields of
the dataset, and a **simulated `pressure` field (hPa)** added to every event — including
replayed historical rows — since the source dataset lacks it (D23). The field is
explicitly labeled as synthetic in the web app and Grafana so real and invented data are
never confused. Timestamps at each hop (`ingest_ts` at producer, processing time at Spark,
write time at Cassandra) are mandatory because end-to-end latency is a required KPI (§9).

### 5.3 Synthetic generation phase
- Activates automatically when the dataset is fully consumed; the transition must be
  visible in the web app and logged.
- Generated values must be statistically plausible continuations of the real data
  (per-device baselines and variances derived from the dataset, day/night patterns for
  temperature and light).
- Configurable anomaly injection (e.g., a value spike with probability p per event) so
  anomaly KPIs have material to detect. Default p = 5% (confirmed).
- Runs indefinitely — this is what feeds the 48-hour endurance run.

### 5.4 Anomaly definition (rule-based, Phase 1)
An event is flagged anomalous when a metric value deviates more than N standard deviations
from that device's rolling mean, or crosses an absolute safety threshold (e.g., smoke/CO
ceiling). N = 3 (confirmed). Exact thresholds per metric to be fixed during
development from the dataset's real distributions.

### 5.5 Note on requested KPI fields
Average/maximum temperature and humidity are directly supported by the dataset.
Atmospheric pressure is not present in the dataset; per D23 it is **simulated for all
rows** (plausible values with daily variation) and visibly labeled as synthetic wherever
it is displayed.

### 5.6 Device metadata and reference thresholds (planner role, D32/D33)

Two new small Cassandra tables support the environmental/planner role, both read once and cached
by the backend rather than queried per request:

- **`device_metadata`** (`device_id` PRIMARY KEY, `name`, `area`, `lat`, `lon`) — static, seeded once
  at schema-init time. Placement is **not arbitrary**: derived from actually analyzing each of the
  3 known devices' 8-day co/lpg/smoke statistics in the source CSV (mean, standard deviation,
  coefficient of variation). `b8:27:eb:bf:9d:51` has the highest mean on all three pollutants with
  low variance (7-10% CV) — a persistently-elevated, not-spiky signature — placed near an active
  road (Kaiserstraße/B70 corridor). `1c:bf:ce:15:ec:4d` has a middling mean but by far the tightest
  distribution (5-8% CV, never spikes across the full 8 days) — placed in a quiet residential/green
  area (Ems-Auen/Baccum). `00:0f:00:70:91:0a` has the lowest mean but by far the highest volatility
  (29-42% CV, sharp occasional spikes) — placed near the Ems river close enough to a road crossing
  to catch intermittent bursts (Konrad-Adenauer-Ring). `motion` is ~0% true for all three devices in
  this dataset and is not a usable signal (an earlier "occupancy-correlated pollution" metric idea
  was dropped for this reason).
- **`device_thresholds`** (`device_id`, `metric`, `mean`, `stddev`, `ceiling`) — written once at
  Spark startup from the exact same `compute_seed_baseline()` output that seeds the streaming
  anomaly detector (§5.4, `spark_job/spark_job/baseline.py`), **not** a separately invented set of
  "safety limits" (D33). The backend's `environment.py` derives per-metric status (ok/warning/
  critical — critical mirrors §5.4's own `|z| > 3` / ceiling rule by construction), an air quality
  score (0-100, worst-pollutant-dominates over co/lpg/smoke, deliberately *not* called "AQI" since
  that name implies the EPA scale where higher means worse — the opposite of this project's
  convention), a comfort index (temp+humidity), and a chronic-exposure ratio from `agg_1h` history.
  One consequence of this design: the planner map's "critical" pin and the admin's anomaly log agree
  for the same device/metric/moment, because they're reading the same numbers.

---

## 6. Use Cases

**UC-1 — Deploy the stack.** The user runs one command (`docker compose up -d`); all
services start; the web app's step 1 shows each container reaching a healthy state.
*Success:* all containers healthy; web app reachable at its local URL; Grafana reachable.

**UC-2 — Guided walkthrough of the pipeline.** The user logs into the web app and follows
the numbered steps: Ingestion → Kafka → Spark → Cassandra → KPIs. At each step the UI
shows live, real data from the running component (recent events, partition offsets and
lag, latest micro-batch statistics, latest rows written).
*Success:* a user with no prior knowledge can explain, after the walkthrough, what was
ingested, how it was transformed, and where it is stored.

**UC-3 — Observe the dataset→synthetic hand-over.** The user watches the moment the Kaggle
replay ends and synthetic generation begins; the UI marks the transition.
*Success:* no interruption in the stream; the transition timestamp is visible.

**UC-4 — Consult KPIs in Grafana.** The user opens Grafana and views the dashboards of §9,
filtered by device and by time range, at both 1-minute and 1-hour granularity.
*Success:* all six KPI families render with live data.

**UC-5 — Run the 48-hour endurance scenario.** The operator starts the pipeline at the
endurance rate and leaves it running for ~2 days. Grafana shows disk growth, write
latency, compaction activity and consumer lag throughout.
*Success:* acceptance criteria of §10 met.

**UC-6 — Inspect an anomaly.** The user finds an anomaly count in the dashboard and drills
down to the affected device/metric/window.
*Success:* every flagged anomaly is traceable to stored rows in Cassandra.

**UC-7 (later phase) — Control the pipeline from the UI.** Start/stop the producer,
trigger a load burst, inject anomalies on demand. Not delivered in Phase 1, but the
backend API and producer must be designed so this only adds endpoints, not redesign.

**UC-8 — Environmental/planner role: check a location's air quality.** A planner (or, in
spirit, a citizen) logs in with the planner account, sees a map of Lingen (Ems) with every
sensor colored by current status, clicks a pin to see its air quality score, comfort
index, chronic-exposure rate over the last 24h, and a trend chart, and reads the
citizen-facing recent-alerts feed for a plain-language explanation of any current
warning.
*Success:* a planner can answer, for any sensor, "is this currently safe, and is it a
persistent problem or a one-off" without reading raw sensor values or knowing anything
about the pipeline underneath.

**UC-9 — Infrastructure/admin role: diagnose a live problem.** An admin logs in, sees a
new alert appear in the Alerts tab (consumer lag, Cassandra write latency, an elevated
service error rate, or a service down), and clicks through to Grafana Explore, landing
directly on the Loki logs for that service and time window — no manual log-hunting across
containers.
*Success:* time from "alert appears" to "root-cause log lines visible" is one click.

---

## 7. Functional Requirements

**Ingestion (FR-I)**
- FR-I1. The producer replays the Kaggle dataset at a configurable rate.
- FR-I2. On dataset exhaustion the producer switches to synthetic mode automatically,
  without stream interruption, preserving the schema.
- FR-I3. Every event carries the timestamps required for end-to-end latency measurement.
- FR-I4. The producer exposes its state (mode, rate, events sent) to the backend API.

**Kafka (FR-K)**
- FR-K1. One topic `sensor-readings` with ≥3 partitions (confirmed), keyed by
  device ID.
- FR-K2. Produced offsets, committed offsets, and per-partition lag are observable by the
  web app and by Prometheus.

**Spark (FR-S)**
- FR-S1. A PySpark Structured Streaming job consumes the topic in micro-batches.
- FR-S2. Two windowed aggregations run concurrently: 1-minute and 1-hour tumbling windows,
  per device and per metric, computing at minimum avg, min, max, count, anomaly count.
- FR-S3. Rule-based anomaly flagging per §5.4.
- FR-S4. Streaming-query progress (batch id, input rows, processing time, watermark) is
  exposed to the web app and Prometheus.

**Cassandra (FR-C)**
- FR-C1. Keyspace `iot` with tables for raw events, 1-minute aggregates, and 1-hour
  aggregates, modeled with time-series partition/clustering keys.
- FR-C2. No TTL: all data is retained (explicit decision; see NFR-4 and Risk R-1).
- FR-C3. Write latency, pending compactions, and data-directory disk usage are exported to
  Prometheus.

**Role-based access (FR-R, D29)**
- FR-R1. The session token carries a `role` claim (`admin` or `planner`), resolved from one
  of two fixed credential pairs (env-var-configured, no user store).
- FR-R2. `GET /api/auth/me` returns the caller's role so the frontend can branch without a
  second request.
- FR-R3. Endpoints scoped to one role (e.g. `GET /api/admin/alerts`) are rejected (403) for
  a session carrying the other role.
- FR-R4. Endpoints useful to both roles (e.g. `GET /api/sensors`, `GET /api/anomalies`) are
  reachable by either role — role gating is about UI surface and admin-only actions, not
  about hiding sensor data from the planner.

**Web application — infrastructure/admin role (FR-W)**
- FR-W1. Guided, sequential step UI covering: deployment status, ingestion, Kafka,
  Spark, Cassandra, and a summary linking to Grafana, under a "Pipeline" tab.
- FR-W2. Observer mode only: no action in the UI mutates pipeline state (Phase 1).
- FR-W3. Live updates (WebSocket or ≤2 s polling) at every pipeline step.
- FR-W4. Role-based login required before any pipeline data is shown (FR-R).
- FR-W5. The step layout and copy must make each stage understandable to a newcomer
  (short explanatory text per step, consistent vocabulary with this document).
- FR-W6. An "Alerts" tab lists recent Grafana-fired alerts (polled from
  `GET /api/admin/alerts`), each with a one-click Grafana Explore drill-down link
  scoped to that alert's service and a recent time window (§4.2).

**Environmental/planner role (FR-E, D32)**
- FR-E1. A map of Lingen (Ems) shows one marker per known device at its
  `device_metadata` location (§5.6), colored by current overall status
  (ok/warning/critical/unknown).
- FR-E2. Clicking a marker shows that device's latest reading, per-metric status, air
  quality score, comfort index, and chronic-exposure ratio and trend direction
  (`GET /api/sensors`, `GET /api/sensors/{device_id}/history`).
- FR-E3. Selecting a device shows a per-metric behavior-over-time view (D34): one chart
  each at minute/hour/day/week resolution (`GET /api/sensors/{device_id}/timeline`),
  with a shaded region over any time span where that metric was outside the acceptable
  range — a visual answer to "was this device okay, and for how long wasn't it," which
  replaced an earlier plain-text recent-alerts feed (superseded design, R2) that didn't
  make chronic-vs-one-off problems legible at a glance.
- FR-E4. Live updates via polling (`GET /api/sensors` — no WebSocket message type was
  added for this role in Phase 1; the backend already broadcasts alert updates over the
  existing channel for a future upgrade, see §4.2).

**Dashboards (FR-G)**
- FR-G1. Grafana ships pre-provisioned (dashboards, data sources, and alert rules as code
  in the repo, loaded automatically at startup — no manual dashboard or alert building).
- FR-G2. Dashboards implement the KPI catalogue of §9.
- FR-G3. Grafana uses its built-in authentication; default credentials must be changed at
  first login.
- FR-G4. Alert rules (consumer lag, Cassandra write latency, elevated per-service ERROR
  log rate, service down) are provisioned as code and route to a webhook contact point
  into the backend (D31, §4.2).

**Deployment (FR-D)**
- FR-D1. One Docker Compose file starts the entire system; a second command stops it.
- FR-D2. All service configuration via environment variables / mounted config files —
  nothing hardcoded — so the same images run unchanged in a future cloud environment.
- FR-D3. Data (Cassandra, Kafka, Prometheus, Grafana) persists in named volumes across
  restarts.

---

## 8. Non-Functional Requirements

- **NFR-1 Performance (baseline).** (confirmed) Sustain 100 msg/s continuously
  with end-to-end latency (event produced → row queryable in Cassandra) ≤ 10 s at p95.
- **NFR-2 Performance (endurance/peak).** (confirmed) Sustain 500 msg/s for
  48 hours (≈ 86 million events) without service failure. "Peak" in this project means
  endurance under sustained load, not maximal burst speed.
- **NFR-3 Host resources (local development).** (confirmed) Minimum host: 16 GB RAM, 4 CPU cores,
  **100 GB free disk** for the endurance run. (Sizing basis: 500 msg/s × 48 h × ~250 B
  ≈ 22 GB raw JSON, amplified by Cassandra storage overhead, aggregates, commit logs,
  Kafka retention, and Prometheus data. At 100 msg/s, 25 GB free disk suffices.)
- **NFR-4 Retention.** Keep everything — no TTL, no automatic deletion. Consequence:
  disk usage grows unboundedly; disk-growth monitoring (KPI-4) and the minimum disk of
  NFR-3 are therefore mandatory, and Risk R-1 applies.
- **NFR-5 Portability.** No dependency on any specific machine beyond Docker:
  configuration externalized (FR-D2), no hardcoded hostnames or IPs in application code,
  secrets injectable via environment. The same images run unchanged in local Compose and
  in the Contabo k3s cluster; only the compose files vs. Kubernetes manifests differ.
- **NFR-11 Deployment security (Contabo, public IP exposure).** Contabo VPS are
  unmanaged — all hardening is our responsibility:
  - Host firewall on all three VPS: default deny inbound; open only SSH (key-only, no
    password auth), the Traefik ingress ports, and the k3s/WireGuard inter-node ports
    restricted to the other two nodes' IPs. Kafka (9092), Cassandra (9042), Spark UI,
    Prometheus, and the backend API are **never** publicly reachable — cluster-internal
    only, enforced by both the firewall and Kubernetes NetworkPolicies.
  - All inter-node traffic (Kafka replication, Cassandra gossip, Spark shuffle,
    Prometheus scrapes, etcd) runs over the flannel **WireGuard backend** (encrypted) —
    never in cleartext over the public interface.
  - Web app and Grafana are reachable only through the Traefik ingress, behind their
    logins, over TLS with a **self-signed certificate** (D25) — the browser warning is
    accepted; plain HTTP would send credentials across the internet in cleartext and is
    not permitted. (Upgrade path if the warning ever bothers demos: a free dynamic-DNS
    subdomain + Let's Encrypt.)
  - Fail2ban (or equivalent) on SSH; automatic OS security updates enabled.
- **NFR-12 Node sizing (Contabo).** (confirmed) Data nodes (VPS-1, VPS-2):
  ≥8 vCPU, ≥24 GB RAM, ≥200 GB NVMe each — with replication factor 2 each data node
  stores the full dataset, so the §NFR-3 disk math applies **per data node**. Control
  node (VPS-3): ≥4 vCPU, ≥8 GB RAM, ≥75 GB NVMe (etcd, KRaft controller, ingress, web
  app, producer, Spark master, Prometheus, Grafana — no bulk data). Note Contabo's
  documented CPU and disk-I/O contention on shared plans: the Cassandra write-latency
  threshold in §10 must be calibrated with a disk/CPU benchmark on the actual VPS before
  the endurance run, and per-pod resource requests/limits are mandatory.
- **NFR-6 Security.** Basic login on web app (role-aware, D29) and Grafana; no ports exposed beyond the
  documented ones; secrets never committed to the repository. (Full hardening — TLS,
  SSO — deferred to the cloud phase.)
- **NFR-7 Observability.** Every component exports metrics to Prometheus; container logs
  accessible via `docker compose logs`.
- **NFR-8 Recoverability.** After a host reboot, `docker compose up -d` resumes the
  pipeline with all previously stored data intact (named volumes, committed Kafka offsets).
- **NFR-9 Documentation.** README covering: prerequisites, one-command start, walkthrough
  guide, endurance-run procedure, and how to reset all data.
- **NFR-10 npm supply-chain security.** Motivated by the 2025–2026 wave of npm
  supply-chain attacks (Shai-Hulud worm 09/2025 and its 2026 successors; axios maintainer
  compromise 03/2026; keyv/cacheable worm 08/2026; ongoing typosquatting and
  dependency-confusion campaigns). Because even top-tier packages have been compromised,
  the policy is process-based, not a blocklist:
  - **NFR-10.1 Minimal dependency tree.** The frontend uses only an explicitly approved
    dependency list (initial allowlist: `react`, `react-dom`, `vite` build tooling, and
    `echarts` — D26; extended to `leaflet` for the planner role's map — D32, justified in
    `frontend/README.md` since it's a runtime, not dev-only, addition). Everything else
    uses browser/Node natives: `fetch` instead of `axios`, native WebSocket, no utility
    micro-packages (lodash-style helpers are written in-project; the map itself uses raw
    Leaflet, not `react-leaflet`, to avoid a second mapping-related dependency). Adding
    any dependency requires a justification recorded in the repository.
  - **NFR-10.2 Lifecycle scripts disabled.** npm installs run with lifecycle scripts
    ignored (`ignore-scripts=true` in the project `.npmrc`); any package that genuinely
    requires an install script must be individually allowlisted and reviewed. Rationale:
    install-time preinstall/postinstall hooks are the dominant execution vector (keyv,
    08/2026).
  - **NFR-10.3 Version cooldown.** No dependency version younger than **14 days**
    (confirmed) is ever installed; exact versions are pinned (no `^`/`~`
    ranges) and the lockfile is committed. CI installs only via `npm ci` against the
    frozen lockfile. Rationale: compromised releases are typically detected within hours
    to days; a cooldown removes the exposure window.
  - **NFR-10.4 Automated scanning (D27).** Three layers: (1) **Socket** — GitHub App
    reports on every PR that changes dependencies, and the Socket CLI gates CI builds
    (fails on flagged malicious packages, npm and PyPI); the free **Socket Firewall**
    protects developer machines at install time. (2) **Trivy** in CI scans container
    images and k3s manifests. (3) `npm audit` / `pip-audit` cover known CVEs.
  - **NFR-10.5 Registry hygiene.** Only the official `registry.npmjs.org` is used; all
    package names are copied from official documentation (never typed from memory) to
    avoid typosquats; no internal/scoped package names that could be dependency-confused.
  - **NFR-10.6 Isolated builds.** The frontend is built inside its Docker build stage
    with no credentials, cloud secrets, or host filesystem access available, so a
    compromised build-time dependency cannot exfiltrate anything of value.
  - **NFR-10.7 Update discipline.** Dependency updates are proposed by an automated tool
    (Dependabot/Renovate) but merged only after manual review, respecting NFR-10.3's
    cooldown. Security patches for actively exploited vulnerabilities are the only
    exception to the cooldown, applied after verifying the advisory from the source.
  - **NFR-10.8 Python parity.** The same principles (pinned versions with hashes,
    lockfile, minimal dependencies, official PyPI only, CI scanning) apply to the Python
    backend, producer, and Spark job — PyPI is experiencing the same class of attacks.
- **NFR-13 Log retention (D30).** Loki's own log volume is retained for **7 days**
  (`limits_config.retention_period` in `infra/loki/loki-config.yml`) — independent of
  NFR-4's "keep everything" policy, which applies to sensor data in Cassandra, not
  operational logs. 7 days is sized for the demo/endurance-run scope of this phase, not a
  compliance retention requirement.

---

## 9. KPI Catalogue (Grafana)

| # | KPI family | Metrics | Source |
|---|---|---|---|
| KPI-1 | Throughput & consumer lag | msgs/s produced, msgs/s consumed, per-partition lag, total events | Kafka exporter → Prometheus |
| KPI-2 | End-to-end latency | p50/p95/max of (Cassandra write time − event production time); per-hop breakdown | Timestamps in events; Spark job → Prometheus |
| KPI-3 | Anomaly metrics | anomalies/min, anomaly rate %, by device and metric, top anomalous device | Spark aggregates in Cassandra |
| KPI-4 | Cassandra health | data-directory disk usage & growth rate, write latency, pending compactions, GC pauses | Cassandra/JMX exporter → Prometheus |
| KPI-5 | Business aggregates (planner role, §5.6) | max/avg temperature, avg humidity, max CO/LPG/smoke, motion & light activity — per device, per 1-min and 1-h window; the same data also drives the planner map's per-device air quality score, comfort index, and chronic-exposure ratio | Cassandra aggregate tables |
| KPI-6 | Infra observability (admin role, D30/D31) | log volume and ERROR rate by service, count of currently-firing alerts by severity | Loki (log queries) + the backend's alert store |

Note: atmospheric-pressure KPIs are computed from the simulated `pressure` field (D23)
and labeled as synthetic in the dashboards.

---

## 10. Endurance-Run Acceptance Criteria (UC-5)

The 48-hour run at the NFR-2 rate passes when:
1. No container crashes or restarts unexpectedly during the run.
2. Consumer lag returns to a stable plateau (no unbounded growth) for the entire run.
3. Cassandra p95 write latency stays under a threshold calibrated from a benchmark run
   on the actual Contabo VPS (confirmed approach; 50 ms initial placeholder, replaced by
   benchmark × safety margin in P6).
4. Disk usage grows linearly and predictably, and its projection is visible in Grafana.
5. End-to-end latency p95 stays within NFR-1's bound throughout.
6. Data written in hour 1 is still fully queryable in hour 48.

---

## 11. Decision Log (agreed during elicitation)

| # | Decision | Choice |
|---|---|---|
| D1 | System nature | Real pipeline (actual Kafka/Spark/Cassandra), not a simulation |
| D2 | Deployment | Local Docker Compose first; designed cloud-ready |
| D3 | Dashboard split | Custom web app for the guided steps; Grafana for KPIs |
| D4 | Data source | Kaggle `garystafford/environmental-sensor-data-132k` replay, then synthetic continuation |
| D5 | "Peak" meaning | ~2-day endurance run that stresses but does not break Cassandra |
| D6 | Language | Python everywhere (PySpark, producer, backend) |
| D7 | Retention | Keep everything; disk growth accepted and monitored |
| D8 | Web-app control | Observer in Phase 1; control panel in a later phase |
| D9 | KPI families | Throughput/lag, end-to-end latency, anomalies, Cassandra health, business aggregates |
| D10 | Windows | 1-minute and 1-hour tumbling windows |
| D11 | Access | Basic login (web app) + Grafana built-in auth; cloud-ready |
| D12 | Frontend / backend split | Frontend in React.js; backend in Python (confirmed) |
| D13 | Supply-chain policy | NFR-10 adopted: allowlisted minimal deps, scripts disabled, 14-day cooldown, pinned lockfile, CI scanning |
| D14 | Deployment target | Two Contabo VPS (unmanaged); local Docker Compose kept for development |
| D15 | Topology | True cluster: Kafka broker + Cassandra node on both data VPS (RF=2); Spark workers on both; see D18 for the 3-node evolution |
| D16 | Orchestration (superseded) | Docker Swarm — superseded by D18 after deciding to add a third node |
| D17 | Exposure | Public via IP addresses, no domain; TLS approach pending (OQ-6) |
| D18 | Orchestration (final) | **k3s on 3 Contabo VPS**: 2 data nodes + 1 small control node; HA control plane (3× etcd) and 3 KRaft controllers solve the coordination quorum; k3s learning curve accepted as an explicit project goal |
| D19 | Workload style | Kafka/Cassandra as plain hand-written StatefulSets with node-pinned local volumes (transparent, lighter); operators deferred to a later phase |
| D20 | Kafka coordination | KRaft (no ZooKeeper) — resolves OQ-4; 3 controllers, one per node |
| D21 | Backend framework | FastAPI confirmed |
| D22 | Numeric parameters | All proposed values accepted (100 msg/s replay; 500 msg/s × 48 h endurance; p=5%; N=3σ; ≥3 partitions; node sizing per NFR-12; 14-day cooldown) |
| D23 | Pressure field | Simulated for ALL rows (including replayed real data), explicitly labeled as synthetic in every display |
| D24 | Raw event storage | Raw events + aggregates both stored in Cassandra (full disk math of NFR-3/NFR-12 stands) |
| D25 | TLS | Self-signed certificate; browser warning accepted; dynamic-DNS + Let's Encrypt noted as future upgrade |
| D26 | In-app charting | Apache ECharts ("impressive" visuals requirement); pipeline-flow animation custom React/SVG; Grafana unchanged |
| D27 | Supply-chain scanning | Socket (PR + CI) + free Socket Firewall (dev machines) + Trivy (images/IaC) + npm audit/pip-audit — chosen by recommendation, user delegated |
| D28 | Replay event_ts | Replayed events are stamped with `event_ts = now()` at production time, same as synthetic events, instead of the source dataset's original 2020 timestamps — otherwise "last N minutes" style queries return nothing throughout the entire replay phase |
| D29 | Role-based access | Two fixed credential pairs (admin/planner), session carries a `role` claim; no user store, no self-service accounts — matches this project's existing env-var-credential pattern |
| D30 | Centralized logs | Grafana Loki + Promtail added to the stack; Promtail tails every container's stdout via Docker service discovery (no per-service logging change needed, everything already emits JSON-line logs); only `container`/`stream`/`level` are indexed labels to avoid cardinality issues |
| D31 | Alerting | Grafana's own provisioned alert rules (reusing metric names already tested in the KPI dashboard) route to a webhook contact point into the backend, which broadcasts over the existing WebSocket channel; each alert links to a client-built Grafana Explore URL for one-click log drill-down, instead of building a bespoke log viewer |
| D32 | Planner map | Leaflet (raw API, not `react-leaflet`) chosen over Mapbox GL/Google Maps for the map view — MIT-licensed, no API key/billing, minimal-footprint, consistent with NFR-10.1's dependency discipline; centered on Lingen (Ems) as the reference municipality |
| D33 | Threshold/AQI data source | The planner role's per-metric status and air quality score reuse the exact same mean/std/ceiling values that seed Spark's own streaming anomaly detector (persisted once at Spark startup into a new `device_thresholds` table), rather than inventing a separate set of "safety limits" — one source of truth for "statistically unusual" and "environmentally in the warning/critical band" |
| D34 | Per-sensor timeline replaces the alert feed | The citizen-facing recent-alerts text list (D32-era) was replaced by four charts (minute/hour/day/week) per selected metric, each with shaded regions over unhealthy time spans, computed from `agg_1m`/`agg_1h` — "day"/"week" are rolled up from `agg_1h` in Python rather than adding two more Cassandra tables purely for a display resolution. Chosen over a text log because the whole point is showing *how long* and *how often* a metric was bad, which a scrolling list of individual events doesn't make legible at a glance |

---

## 12. Open Questions — ALL RESOLVED (kept for traceability)

- ~~OQ-1 — Atmospheric pressure.~~ **Resolved (D23):** simulated for all rows, labeled
  synthetic.
- ~~OQ-2 — Proposed values.~~ **Resolved (D22):** all accepted.
- ~~OQ-3 — Web app backend framework.~~ **Resolved (D21):** FastAPI.
- ~~OQ-4 — Kafka coordination.~~ **Resolved (D20): KRaft.** With three nodes available,
  a 3-controller KRaft quorum is strictly simpler and more robust than adding a
  ZooKeeper ensemble as a separate StatefulSet.
- ~~OQ-5 — Raw events in Cassandra.~~ **Resolved (D24):** raw + aggregates in Cassandra.
- ~~OQ-6 — TLS without a domain.~~ **Resolved (D25):** self-signed certificate, browser
  warning accepted; free dynamic-DNS subdomain + Let's Encrypt recorded as the upgrade
  path.
- ~~OQ-7 — Third mini-node for quorum.~~ **Resolved (D18): third node adopted** as a
  small control node; coordination quorum is now HA. Remaining nuance is documented in
  §4.1: Cassandra stays RF=2 across the two data nodes, so QUORUM-level survival of a
  data-node loss would need a future RF=3 upgrade.

---

## 13. Risks

- **R-1 — Disk exhaustion (High).** "Keep everything" + endurance load will fill the disk
  eventually; if the disk fills mid-run, Cassandra fails ungracefully. Mitigation: NFR-3
  minimum disk, KPI-4 growth-rate panel with projection, documented reset procedure.
- **R-2 — Local resource contention (Medium).** Kafka + Spark + Cassandra + monitoring on
  one laptop compete for RAM; Cassandra is sensitive to memory pressure. Mitigation:
  explicit per-container memory limits in Compose; NFR-3 sizing.
- **R-3 — Synthetic realism (Medium).** If synthetic data is statistically naive, KPIs and
  anomaly detection become meaningless after hand-over. Mitigation: derive generator
  parameters from the real dataset (§5.3) and validate distributions before Phase 1 ends.
- **R-4 — Endurance-run duration (Low).** A 48-hour test blocks the machine for 2 days.
  Mitigation: a compressed "rehearsal" profile (e.g., 2 h at higher rate) to validate the
  setup before committing to the full run.
- **R-5 — npm/PyPI supply-chain compromise (High likelihood ecosystem-wide, Medium impact
  here).** Self-replicating worms and maintainer-account takeovers have hit even
  foundational packages (axios 03/2026, keyv 08/2026); a compromised dependency executing
  at install or build time could steal credentials from the developer machine or CI.
  Mitigation: full NFR-10 policy (minimal allowlisted dependencies, lifecycle scripts
  disabled, 14-day version cooldown, pinned lockfile + `npm ci`, CI scanning, isolated
  credential-free builds). Residual risk accepted: a compromise older than the cooldown
  window that evades scanners.
- **R-6 — Contabo shared-resource contention and public exposure (Medium).** Contabo's
  high-density model means vCPU and disk I/O can degrade when neighbors are busy —
  directly affecting Cassandra write latency and endurance-run results — and unmanaged
  public VPS are scanned and attacked constantly from day one. Mitigation: benchmark
  before setting §10 thresholds (NFR-12); interpret latency anomalies against node-level
  metrics (CPU steal is visible in Prometheus/node-exporter); full NFR-11 hardening from
  the first boot, before any service is deployed.
- **R-7 — Grafana alerting provisioning (RESOLVED — live-verified).** The provisioned
  alert rules (`infra/grafana/provisioning/alerting/*.yaml`, D31) were confirmed
  against a real `docker compose up`: Grafana logged `"finished to provision
  alerting"` with zero errors, two rules genuinely fired during the stack's own
  startup transient (`service-down` on `spark-job`, `consumer-lag-high`), both reached
  the backend's webhook and appeared correctly in the admin Alerts tab with working
  Grafana Explore drill-down links showing real log lines. One real bug *was* found and
  fixed in this pass — not the alert rules themselves, but the `loki` service's Docker
  healthcheck, which used `wget` against an image that ships no shell at all; see
  `docs/TROUBLESHOOTING.md` P8 §1. Residual risk: this was one local run, not a
  multi-day soak — the endurance run (§10) will be the real stress test.
- **R-8 — Public OpenStreetMap tile server fair-use limits (Low, local/demo scope).**
  The planner map (D32) fetches tiles directly from `tile.openstreetmap.org`, which has
  a documented fair-use policy not meant for sustained high-traffic production use.
  Confirmed working for local development and demonstration (live-verified: real map
  tiles of Lingen (Ems) rendered correctly with status-colored pins). A future cloud
  deployment (P6-adjacent) serving real public traffic should switch to a paid tile
  provider or a self-hosted tile cache before going live.

---

## 14. Suggested Development Phases (for Claude Code)

1. **P1 — Foundation:** Compose stack up (Kafka, Cassandra, Spark, Prometheus, Grafana),
   healthchecks, volumes, schema creation.
2. **P2 — Ingestion:** producer with replay + synthetic modes and hand-over.
3. **P3 — Processing:** Spark job (validation, anomalies, dual windows, Cassandra sink).
4. **P4 — Observability:** exporters wired, Grafana dashboards provisioned (KPI-1…5;
   KPI-6 and alerting added in P8/R3-R4).
5. **P5 — Web app:** FastAPI read-only API + React guided UI + basic login.
6. **P6 — VPS deployment:** provision & harden all three Contabo VPS (NFR-11), install
   k3s in HA mode with the WireGuard flannel backend, benchmark disk/CPU (fixes the §10
   latency threshold), apply the manifests (StatefulSets, ingress, NetworkPolicies),
   verify cluster behavior (replication visible, single-node failure demo).
7. **P7 — Endurance:** rehearsal run, tuning, full 48-hour run on the VPS cluster
   against §10 criteria.
8. **P8 — Role-based redirect (this document's v2.0):** R0 replay-timestamp fix (D28);
   R1 role-based auth + `device_metadata`/`device_thresholds` + `/api/sensors` (D29,
   D33); R2 Leaflet map for the planner role (D32); R3 Loki + Promtail for the admin
   role's centralized logs (D30); R4 Grafana alerting + webhook + admin Alerts tab with
   Explore drill-down (D31); R5 this requirements rewrite. Risks R-7/R-8 flag what's not
   yet live-verified.

Each phase should end in a runnable, demonstrable state.
