# Streaming Sensor Pipeline — Requirements Document (v2.0)

**Project:** Role-based environmental sensor platform for the municipality of Lingen (Ems) — an
infrastructure/admin role (pipeline health, centralized logs, alerting) and an environmental/planner
role (live sensor map, air quality/comfort scoring, citizen-facing warnings), both served from the
same streaming pipeline and KPI dashboard.
**Status:** **v3.0 — approved for development.** v1.0's technical pipeline (Kafka/Spark/Cassandra) is
unchanged; v2.0 redirected the *purpose* the two user-facing surfaces serve (D29-D33); v2.1 responds to
external review feedback on the v2.0 build (D38-D41); v2.2 adds a Cassandra storage-capacity control to
the admin role (D42); v3.0 replaces Docker Compose with Kubernetes (k3d locally) as the deployment
mechanism for the whole stack, closing the Docker-socket privilege D42 introduced and turning the
previously-aspirational P6 k3s architecture into something that actually runs (D43).
**Date:** 2026-08-14 (v1.0), 2026-08-21 (v2.0), 2026-09-16 (v2.1, v2.2, v3.0)
**v0.2 changes:** frontend (React.js) and backend (Python) confirmed; added NFR-10 npm supply-chain security policy and Risk R-5, based on the 2025–2026 npm attack landscape (Shai-Hulud worm and successors, axios and keyv compromises).
**v0.3 changes:** deployment target defined — two Contabo VPS orchestrated with Docker Swarm, true-cluster topology (Kafka broker + Cassandra node on both machines, replication factor 2), public exposure via IP address; added §4.1 deployment topology, NFR-11/NFR-12, Risk R-6, OQ-6/OQ-7.
**v0.4 changes:** orchestrator switched from Docker Swarm to **k3s** on **three** Contabo VPS (2 data nodes + 1 small control node; HA control plane with 3-member etcd; 3 KRaft controllers), Kafka/Cassandra as plain StatefulSets; OQ-7 resolved; OQ-4 resolved as KRaft; D16 superseded by D18/D19; NFR-11/NFR-12 and phases updated.
**v1.0 changes:** all remaining open questions closed — FastAPI confirmed (D21); all proposed numeric values accepted (D22); atmospheric pressure simulated for all rows, labeled synthetic (D23); raw events + aggregates in Cassandra confirmed (D24); TLS via self-signed certificate (D25); charting with Apache ECharts (D26); supply-chain scanning with Socket + free Socket Firewall + Trivy (D27).
**v2.0 changes:** reviewing the actual assignment brief (`development_notes/Assignments_Portfolio_DLBDSEDE02.pdf`) surfaced a drift — the system had become a pipeline-mechanics demo, when the brief's real scenario is a municipality using sensor data to inform planners and warn citizens. Redirected around two roles instead of one guided tour: **infrastructure/admin** (D28 replay-timestamp fix so "last N minutes" queries work from the start of a run; D29 role-based auth; D30 Loki + Promtail centralized logs; D31 Grafana alerting with a webhook into the backend and Explore drill-down links) and **environmental/planner** (D32 a Leaflet map of Lingen (Ems) with data-derived, not arbitrary, sensor placement; D33 threshold/AQI logic that reuses Spark's own baseline statistics rather than inventing separate numbers). §1, §2, §6, §7, and §9 updated accordingly; §3-5 and §10-14 extended, not replaced.
**v2.1 changes:** external review of the running v2.0 build (recorded privately, not committed to the repo) surfaced three concrete gaps rather than new feature requests: (1) no way to compare a current reading against an earlier period, and no described per-role usage narratives beyond the one-line UC success criteria; (2) the admin role's health coverage has no defined path for the disk-exhaustion failure mode already flagged as Risk R-1; (3) nothing in the running system lets a user tell whether a displayed reading is live/synthetic or replayed-real, or when a replayed reading was *actually* collected — a direct consequence of D28 discarding the dataset's original timestamps. Addressed by: D38 (`source_ts` provenance field + a standalone Dataset Explorer view on the source CSV's own real 2020 timeline, shared by both roles); D39 (a compare-to-earlier-period overlay on the existing behavior-over-time charts, falling back to the Dataset Explorer when the compared period predates the live deployment's own history); D40 (a disk-usage-critical alert plus a narrow, explicit, admin-triggered archive-and-trim action — the first Phase-1 exception to the "observer mode only" control-panel deferral); D41 (concrete per-role scenario narratives in the docs site, not just UC one-liners). §2, §5, §6, §7, §8, §9, and §13 updated accordingly.
**v2.2 changes:** a follow-up conversation about Kafka/Cassandra storage limits surfaced that this
project had never given Cassandra's own disk usage a dedicated, node-level signal (only the
whole-host-filesystem alert from D40) or an admin-facing way to actually add capacity — Cassandra's
ring/gossip design makes "add a node, let token ranges rebalance" the real, standard way it scales
storage, unlike Kafka. D42 adds a Storage_Load-based usage control (per-node bytes already scraped by
the existing JMX exporter, compared against a configured budget — a monitored threshold, not a
kernel-enforced quota, since Docker Desktop's WSL2 backend doesn't support per-volume filesystem
quotas) and an admin-triggered "deploy a new Cassandra node" action with live step-by-step progress,
the second explicit, scoped exception to the observer-mode/control-panel deferral (after D40) and the
first to require a new privilege (Docker socket access) rather than only mutating the app's own data
store. §2, §4, §5, §6, §7, §8, and §13 updated accordingly.
**v3.0 changes:** D42's Docker socket exception (NFR-15/R-9) prompted the obvious next question — why
give the backend host-root-equivalent access at all, when Kubernetes' own RBAC exists precisely to
scope this kind of thing narrowly? Rather than patch around it, D43 adopts Kubernetes for the whole
stack: **k3d** (k3s-in-Docker) locally, the same distribution already chosen for production (D18), so
local dev and the eventual Contabo VPS cluster share one set of manifests instead of two unrelated
deployment stories. Cassandra and Kafka become StatefulSets, everything else Deployments (node-exporter
and promtail become DaemonSets, matching their per-node nature), one-shot setup becomes Jobs, and D42's
node-deploy action is reimplemented against the Kubernetes API (scale the StatefulSet, watch pod
readiness, exec `nodetool status` via the k8s exec API) through a narrowly-scoped ServiceAccount +
RBAC Role instead of the Docker socket — closing R-9 entirely rather than just documenting around it.
A new admin "Kubernetes status" panel surfaces pod/StatefulSet health the same way the Deployment step
already surfaces container health. Docker Compose stays in the repo as historical reference (README's
Quick Start now describes the k3d path); nothing about the pipeline's own logic (producer, Spark job,
backend business logic) changes — this is a deployment-mechanism swap, not a rewrite. §2, §3, §4, §5,
§6, §7, §8, §13, and §14 updated accordingly.
**D43 is live-verified**, not just statically checked: a full `k8s/local-up.sh` run on a real k3d
cluster surfaced and fixed five real bugs a live control plane is needed to catch — a `.env`-parsing
crash in the Secret-generation step, Kubernetes' automatic per-Service env-var injection colliding with
Spark's own `SPARK_MASTER_PORT`, a RollingUpdate-vs-single-spark-worker deadlock (now `Recreate`), the
Spark driver advertising an unresolvable bare pod hostname to its executors instead of its pod IP, and —
found after a longer run — Kafka's own readiness/liveness probes spawning a fresh JVM every 10s
(`kafka-broker-api-versions.sh`) that missed its own timeout under host resource pressure and
self-inflicted a `CrashLoopBackOff` (now a plain `tcpSocket` check, matching every other pod's own
`nc -z kafka 19092` readiness assumption). With those fixed, `kubectl -n iot-pipeline get pods` shows
every workload `1/1 Running`/`Completed`, and the app was confirmed end-to-end in the browser: live row
counts flowing through the Pipeline Console's Deployment/Cassandra steps and the new Kubernetes status
panel reading real pod health.

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
- **Data provenance (D38):** a `source_ts` field carried alongside every replayed event, and a
  standalone **Dataset Explorer** view — reachable by both roles — that browses the original Kaggle
  CSV on its own real 2020 timeline, independent of the live Cassandra store.
- **Historical comparison (D39):** a compare-to-earlier-period overlay on the planner's existing
  behavior-over-time charts (§FR-E3), spanning both the live/synthetic history and, once a compared
  period predates that history, the Dataset Explorer's real data.
- **Disk-pressure remediation (D40):** a disk-usage-critical Grafana alert (extends FR-G4), and one
  narrow, explicit, admin-triggered **archive-and-trim** action — export the oldest raw-event
  partitions to a local archive file, then drop them from Cassandra. This is the one Phase-1 exception
  to the control-panel deferral below: a single, logged, capacity-emergency action, not a general
  start/stop/inject control surface.
- **Documented per-role scenarios (D41):** concrete action/reading walkthroughs for both roles in the
  docs site, beyond the existing UC list's one-line success criteria.
- **Cassandra storage capacity control (D42):** a per-node storage-usage display (Storage_Load vs. a
  configured budget) and an admin-triggered "deploy a new Cassandra node" action with live
  step-by-step progress, so a second node genuinely joins the existing ring and appears in the
  deployment map — the second scoped exception to the control-panel deferral below.
- **Kubernetes deployment, local and production (D43):** the whole stack runs on Kubernetes —
  **k3d** locally, the same k3s distribution already chosen for production (D18) — instead of Docker
  Compose. D42's node-deploy action is reimplemented against the Kubernetes API (RBAC-scoped
  ServiceAccount) instead of the Docker socket, closing R-9. A new admin "Kubernetes status" panel
  shows pod/StatefulSet health.
- Grafana dashboards for the KPI catalogue of §9 (now six families, not five).
- Basic login on the web application (now role-aware); Grafana's built-in authentication.
- 48-hour endurance-run scenario, with acceptance criteria (§10).

### Out of scope (Phase 1 — planned for later phases)
- Web-app **control panel** (start/stop flows, trigger bursts, inject anomalies from the UI), **except**
  the narrow archive-and-trim admin action of D40 (a single logged capacity-emergency operation) and
  D42's Cassandra node-deploy action (standing up a new ring member) — two scoped, single-purpose
  exceptions, not a general control surface. The backend API must be designed so broader control-panel
  actions can be added without redesign.
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
| Containerization | Docker / containerd | Same images run locally (k3d) and on the production k3s cluster; Docker Compose (D1-D42 era) stays in the repo as historical reference only, superseded by D43. |
| Orchestration | Kubernetes — **k3d** (k3s-in-Docker, single node) locally, **k3s** (3 nodes, HA embedded etcd) in production (D43, D18) | One manifest set, two environments via Kustomize overlays; Kafka and Cassandra as plain StatefulSets with persistent volumes; flannel WireGuard backend encrypts inter-node traffic in production. |
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
  Cassandra node by default; the k3s manifests are the production deployment contract. D42 adds an
  admin-triggered path to a second Cassandra node *within* that local Compose environment (§4.3) —
  a capacity-scaling illustration, not a redefinition of the local topology's default shape.

### 4.3 Admin-triggered Cassandra node deploy (D42)

Cassandra's gossip/token-ring design makes "add a node, let the ring rebalance" the standard way it
scales storage — unlike Kafka, where a new broker only helps once partitions are explicitly
reassigned to it. The admin role's Pipeline/Deployment view gets a storage-usage control (§5.8) and a
"Deploy new Cassandra node" action:

1. Backend creates and starts a new Cassandra container via the Docker Engine API (the backend
   container gets `/var/run/docker.sock` mounted for this — see NFR-15), reusing the existing node's
   image, environment (`CASSANDRA_CLUSTER_NAME`, DC, `GossipingPropertyFileSnitch`), and network,
   with `CASSANDRA_SEEDS` pointing at the existing node so it joins the same ring, on a fresh named
   volume.
2. Progress is pushed to the admin over the existing pipeline-state WebSocket channel (§4.2's
   pattern) as a small step sequence: creating container → container healthy → visible in
   `nodetool status` as a full ring member (`UN`) → done, with a clear error state if any step
   fails or times out.
3. Token ranges rebalance automatically on bootstrap regardless of the keyspace's replication
   factor (RF only controls replica *count*, not range ownership) — RF stays at 1 for local dev
   (§7 FR-C1's existing value), no `ALTER KEYSPACE` needed for the new node to take over part of the
   original node's range.
4. Reclaiming the disk space the original node no longer owns requires `nodetool cleanup` on it —
   documented as a manual follow-up step (`docs/operations.html`), not automated by this action:
   automating a data-redistribution side-effect without a human decision point is a bigger step than
   this pass takes on (see D42 in §11).
5. Once healthy, the new node appears in the Deployment step's health grid automatically — that grid
   moves from a fixed configured service list to also discover any running `cassandra-*` containers
   via the Docker API (FR-W1).

**Superseded by D43 (§4.4):** point 1's Docker socket mechanism is replaced by the Kubernetes API;
points 2-5's behavior and UX are unchanged, just re-backed.

### 4.4 Kubernetes deployment — local (k3d) and production (k3s) (D43)

D42 gave the backend host-root-equivalent Docker socket access to deploy a Cassandra container — a
real, documented risk (NFR-15, R-9), accepted at the time as scoped and local-only. D43 removes the
need for it entirely by moving the whole stack onto Kubernetes, where RBAC already exists to grant
exactly the narrow capability D42 actually needs ("scale one named StatefulSet, exec into its pods")
without host-level privilege. This also stops treating the production k3s architecture (§4.1) as
aspirational: the same manifests now run locally too.

**Local runtime:** **k3d** (k3s packaged to run as Docker containers) — one single-node cluster,
chosen over Docker-Desktop's built-in Kubernetes or minikube specifically because it *is* k3s, the
already-chosen production distribution (D18), so nothing about the deployment model changes between a
laptop and the Contabo cluster except cluster topology. Images already built via each service's
existing `Dockerfile` are loaded into the k3d cluster with `k3d image import` — no container registry
needed for local dev.

**Workload mapping** (from the D1-D42-era `docker-compose.yml`, one-for-one):

| Compose service | Kubernetes object | Why |
|---|---|---|
| `cassandra`, `kafka` | StatefulSet | Stable per-replica identity + PersistentVolumeClaim — exactly what D42's node-deploy needs, natively |
| `backend`, `producer`, `spark-master`, `spark-worker`, `spark-job`, `grafana`, `prometheus`, `loki`, `kafka-exporter`, `kafka-ui` | Deployment | Stateless-ish, single replica, standard rolling updates |
| `node-exporter`, `promtail` | DaemonSet | Genuinely per-node (host metrics, per-node container logs) — one-per-node is the correct shape now and later on the multi-node VPS cluster, not an arbitrary choice |
| `kafka-volume-init`, `spark-job-volume-init`, `archive-volume-init` | *(removed)* | Their whole job was fixing volume ownership for a non-root process — Kubernetes' pod `securityContext.fsGroup` does this natively on mount, no init container needed |
| `kafka-topic-init`, `cassandra-schema-init`, `dataset-init` | Job | One-shot setup, unchanged in substance; downstream pods gain a small `initContainer` that polls for the dependency (same retry-loop pattern `cassandra-schema-init` already used internally), since Kubernetes has no native "wait for this Job" the way Compose's `condition: service_completed_successfully` does |

**Config and secrets:** the non-secret environment variables already in `docker-compose.yml` become one
ConfigMap per service (or a shared one where values overlap); `GRAFANA_ADMIN_PASSWORD`,
`BACKEND_ADMIN_PASSWORD`, `BACKEND_PLANNER_PASSWORD`, `BACKEND_SESSION_SECRET`, and the optional Kaggle
credentials become a Secret generated from the existing `.env` file at apply time — `.env` stays the
one place these values are set, not duplicated into a second file.

**Storage:** each current named Docker volume becomes a PersistentVolumeClaim against k3d's default
`local-path` StorageClass. A fresh local k3d cluster starts with empty PVCs — same consequence as
`docker compose down -v`, not a live migration of existing local data.

**RBAC (closes R-9):** a `backend` ServiceAccount in the `iot-pipeline` namespace, bound via a
namespaced Role (not ClusterRole) to: `get`/`list`/`watch` on `pods` and `statefulsets` (the new
Kubernetes-status panel, FR-K1), `patch` on the `cassandra` StatefulSet's `/scale` subresource *only*
— `resourceNames: ["cassandra"]`, not "any StatefulSet" (D42's node-deploy action, FR-N2), and
`create` on `pods/exec` for `nodetool status` polling. No cluster-wide permissions, ever.

**Exposure:** only the backend web app (8000) and Grafana (3000) are reachable from the host, via k3d's
port mapping at cluster-create time — mirroring NFR-11's "only what's needed is externally reachable"
stance already applied to the production topology. Everything else (Kafka, Cassandra, Spark UIs,
Prometheus, Loki) is cluster-internal, reached via `kubectl port-forward` when actually debugging it,
same as they're firewalled from the public internet in production (NFR-11).

**Deliberately not done in this pass** (matches D19's "no more machinery than this phase needs"):
Helm (plain YAML/Kustomize is enough at this size, and keeps manifests as transparent and diffable as
the hand-written StatefulSets already were), Operators (Strimzi/K8ssandra — still deferred, D19),
HorizontalPodAutoscaler or Cluster Autoscaler (nothing here should scale itself; D42/D43's Cassandra
capacity action is deliberately a human decision, not automatic), a multi-node local cluster (single
k3d node is sufficient locally; the real multi-node HA topology stays §4.1's production-only concern),
and actually provisioning the Contabo VPS cluster itself (real infrastructure, credentials, and DNS —
a separate operational effort from writing manifests, still tracked as P6 in §14).

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

Every event also carries a nullable **`source_ts`** (D38): for a row produced during the replay
phase, the dataset's own original collection timestamp for that row (2020, per §5.1); `null` for
synthetic rows, which have no real-world collection moment. `source_ts` is purely descriptive
metadata — it is never used for windowing, ordering, or any query logic (that stays on
`event_ts`/`ingest_ts` per D28); its only job is answering "when was this actually collected,"
which `event_ts` alone cannot do once D28 rewrites it to the production moment.

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

### 5.7 Dataset Explorer and historical comparison (D38/D39)

Two features address the "how does live data relate to the dataset" and "no way to compare across
time" feedback together, since both are fundamentally about giving a user access to *a real point in
time other than now*:

- **Dataset Explorer.** A read-only view, reachable by either role (`GET /api/dataset/*`), that
  browses the original Kaggle CSV directly — not through Kafka/Spark/Cassandra — on its own real
  timeline: 3 devices, ~405,000 readings, 7 days in 2020 (§5.1). It reads the same file the
  `dataset-init` container already fetched into the `kaggle_dataset` volume, so no new ingestion path
  or duplicate storage is needed. Every reading shown here displays its true original timestamp, never
  `event_ts`. This is the direct answer to "is there one version live and one version per dataset":
  yes, and now both are separately inspectable.
- **Historical comparison overlay.** Extends the planner's per-metric behavior-over-time charts
  (§FR-E3) with a "compare to" control (an hour/day/week/month/year ago, matching the chart's own
  resolution). The backend resolves the compared period against whichever source actually has data for
  it: live/synthetic history from Cassandra when the period falls within the deployment's own running
  time, or the Dataset Explorer's real data when it predates that (e.g. comparing "now" against "the
  same time of year" necessarily means the 2020 dataset window, not a fabricated year of live history).
  The overlay is explicitly labeled with which source answered it, so a planner is never shown two
  numbers without knowing they come from different eras.

### 5.8 Cassandra storage-usage control (D42)

Per Cassandra node, `org.apache.cassandra.metrics:type=Storage,name=Load` (bytes of data that node
currently holds) is already scraped by the existing JMX exporter (§3, `infra/cassandra/jmx-exporter/`)
into Prometheus — D42 is the first thing to actually display it. The admin UI shows each node's usage
as a percentage of a **configured budget** (`CASSANDRA_NODE_STORAGE_BUDGET_BYTES`, env-var, documented
default): explicitly a monitored threshold the admin compares Cassandra's own reported usage against,
**not** a kernel-enforced filesystem quota — Docker Desktop's WSL2 backend doesn't support
per-container/per-volume storage quotas (`--storage-opt size=` needs devicemapper or
overlay2-on-XFS-with-pquota; neither is the local dev default), so a real hard cap would need a
loopback-mounted fixed-size volume, out of scope for what this control needs to illustrate.

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

**UC-10 — Either role: compare a reading against an earlier period.** From a device's
behavior-over-time chart, the user picks a "compare to" offset (a day/week/month/year ago). The chart
overlays the earlier period, sourced from live history or the Dataset Explorer as needed (§5.7), and
labels which source it used.
*Success:* a user can tell, for any metric, whether current conditions are typical for that
time-of-day/week/year or a departure from it — without manually cross-referencing two separate views.

**UC-11 — Admin: remediate a disk-full risk.** A disk-usage-critical alert fires in the Alerts tab
(D40). The admin drills into Grafana Explore to confirm which node/table is growing fastest, then uses
the archive-and-trim action to export the oldest raw-event partitions to a local archive file and drop
them from Cassandra, freeing space without an unqualified data-loss reset.
*Success:* disk usage drops below the alert threshold, the alert clears, and the archived data remains
recoverable from the exported file — not silently destroyed.

**UC-12 — Admin: add Cassandra storage capacity.** An admin notices a Cassandra node's storage-usage
control approaching its configured budget (D42), clicks "Deploy new Cassandra node," and watches live
step-by-step progress (container created → healthy → joined the ring) in the admin UI. Once done, the
new node appears in the Deployment step's health grid alongside the original.
*Success:* a second Cassandra node is visibly part of the running cluster, `nodetool status` on either
node shows both as full (`UN`) members, and the admin can see this happened without guessing at
container/cluster internals from a terminal.

**UC-13 — Admin: check Kubernetes status.** An admin opens the new Kubernetes-status panel and sees
every pod's phase, readiness, restart count, and node, plus each StatefulSet/Deployment's desired vs.
ready replica counts — the same "is the deployment actually healthy" question the Deployment step
already answers for individual services, now answerable at the orchestration layer too.
*Success:* a pod stuck `Pending` (e.g. an unschedulable second Cassandra replica, insufficient cluster
memory) is visibly distinguishable from one that's `CrashLoopBackOff`, without a terminal.

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
  aggregates, modeled with time-series partition/clustering keys. The raw-events table
  includes the nullable `source_ts` column (D38, §5.2).
- FR-C2. No TTL: all data is retained by default (explicit decision; see NFR-4 and Risk
  R-1), with the D40 archive-and-trim action as the sole, explicit, admin-triggered
  exception for capacity emergencies.
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
  Spark, Cassandra, and a summary linking to Grafana, under a "Pipeline" tab. The deployment status
  step's health grid combines its fixed configured service list with any running `cassandra-*`
  containers discovered via the Docker API (FR-N3, D42), so an admin-deployed extra node appears
  without a web-app redeploy.
- FR-W2. Observer mode only: no action in the UI mutates pipeline state (Phase 1), except the scoped
  exceptions in FR-A (D40) and FR-N (D42).
- FR-W3. Live updates (WebSocket or ≤2 s polling) at every pipeline step.
- FR-W4. Role-based login required before any pipeline data is shown (FR-R).
- FR-W5. The step layout and copy must make each stage understandable to a newcomer
  (short explanatory text per step, consistent vocabulary with this document).
- FR-W6. An "Alerts" tab lists recent Grafana-fired alerts (polled from
  `GET /api/admin/alerts`), each with a one-click Grafana Explore drill-down link
  scoped to that alert's service and a recent time window (§4.2).
- FR-W7. A "Docs" tab (D36/D37) embeds the project's own local documentation site
  (`docs/index.html` and its linked pages — architecture/containers, deployment, operations &
  troubleshooting, file reference) via an admin-gated static-file route
  (`GET /api/admin/docs-site/{path}`), bundled into the backend image at build time, so an
  administrator sees exactly the same pages a developer opens directly via `file://`, no repo
  checkout needed. `REQUIREMENTS.md` and root `README.md` stay repository-only, cross-linked from
  the docs site rather than duplicated into it.
- FR-W8. A "Dataset Explorer" is reachable from both role UIs (D38, §5.7), browsing the source
  CSV on its own real timeline independent of the live pipeline.

**Admin capacity-remediation action (FR-A, D40)**
- FR-A1. `POST /api/admin/archive` triggers the archive-and-trim action: the oldest raw-event
  partitions (a caller-specified cutoff, or a sane default such as the oldest 10% by time) are
  exported to a local archive file (path under a dedicated named volume) before being deleted
  from Cassandra. This is the sole write/mutate action available to either role in Phase 1 — the
  one explicit exception to FR-W2's observer-mode rule, and to the control-panel deferral in §2.
- FR-A2. The action is logged (structured log line, picked up by Loki/Promtail per D30) with the
  cutoff used, row/partition count, and archive file path, and the action itself, and its
  before/after disk usage, are visible in the admin Alerts/Pipeline tabs.
- FR-A3. The action is only reachable by the admin role (FR-R3) and requires an explicit
  confirmation step in the UI before executing, since it is irreversible against the live store
  (the archive file is the only remaining copy).

**Cassandra node scale-out (FR-N, D42)**
- FR-N1. `GET /api/admin/cassandra/storage` returns each known Cassandra node's `Storage_Load` (bytes)
  and the configured budget, so the admin UI can render a usage percentage per node.
- FR-N2. `POST /api/admin/cassandra/nodes` (admin-only, FR-R3) scales the `cassandra` StatefulSet's
  replica count via the Kubernetes API (D43, §4.4 — superseding D42's Docker-socket approach), joins
  the new pod to the existing ring (§4.3), and streams step-by-step progress over the existing
  pipeline-state WebSocket channel (§4.2) rather than making the caller poll. The progress UI is a
  genuine animated visual, not a static text list — in the spirit of D26's existing "impressive
  visuals" pipeline-flow animation (`PipelineFlowDiagram.tsx`) — so a resilient admin watching it has
  no doubt the process is actively running versus stalled or failed at each step
  (pod scheduling → healthy → joining the ring → done), with a clearly distinct failure state if
  any step times out or errors.
- FR-N3. The Deployment step's health grid (FR-W1) discovers all `cassandra` StatefulSet pods via the
  Kubernetes API (D43) in addition to its fixed configured service list, so a newly joined node
  appears without a redeploy of the web app.
- FR-N4. Reclaiming the original node's now-unowned disk space (`nodetool cleanup`) is documented as
  a manual operator step, not triggered by FR-N2 (§4.3 point 4) — a deliberate scope boundary, not an
  oversight.

**Kubernetes visibility (FR-K, D43)**
- FR-K1. `GET /api/admin/kubernetes/status` (admin-only, FR-R3) returns every pod's phase, readiness,
  restart count, and node, plus each StatefulSet/Deployment's desired vs. ready replica counts, via the
  same read-only RBAC grant FR-N1/FR-N3 already use — one Kubernetes-status panel in the admin UI
  (UC-13), not a generic cluster dashboard bolted on.
- FR-K2. The backend's Kubernetes API access is scoped to a single namespaced Role (§4.4) — no
  ClusterRole, no permissions beyond what FR-N1-N4 and FR-K1 actually need.

**Environmental/planner role (FR-E, D32)**
- FR-E1. A map of Lingen (Ems) shows one marker per known device at its
  `device_metadata` location (§5.6), colored by current overall status
  (ok/warning/critical/unknown).
- FR-E2. Clicking a marker shows that device's latest reading, per-metric status, air
  quality score, comfort index, and chronic-exposure ratio and trend direction
  (`GET /api/sensors`, `GET /api/sensors/{device_id}/history`).
- FR-E3. Selecting a device shows a per-metric behavior-over-time view (D34): one chart
  each at minute/hour/day/week/month resolution (D35 added month;
  `GET /api/sensors/{device_id}/timeline`), with a shaded region over any time span
  where that metric was outside the acceptable range — a visual answer to "was this
  device okay, and for how long wasn't it," which replaced an earlier plain-text
  recent-alerts feed (superseded design, R2) that didn't make chronic-vs-one-off
  problems legible at a glance.
- FR-E4. Live updates via polling (`GET /api/sensors` — no WebSocket message type was
  added for this role in Phase 1; the backend already broadcasts alert updates over the
  existing channel for a future upgrade, see §4.2).
- FR-E5. Below the charts, an out-of-range log (D35) lists the specific periods a
  selected metric breached its acceptable range, scoped independently at
  minute/hour/day/week/month resolution — newest first, each entry showing the actual
  breaching value (the window's min or max, whichever deviated furthest, not its
  smoothed average) against the normal band or safety ceiling it crossed, in plain
  language. Complements FR-E3 rather than replacing it: the charts answer "how long and
  how often," the log answers "which exact reading, and by how much."
- FR-E6. A "compare to" control on FR-E3's charts (D39, §5.7) overlays an earlier period (a
  day/week/month/year, matching the chart's resolution) onto the current one, resolving the data
  from live/synthetic history or the Dataset Explorer as needed, and labeling which source
  answered — so a planner can tell whether "now" is typical for that time-of-day/week/year.

**Data provenance and historical browsing (FR-P, D38)**
- FR-P1. Every reading shown in the planner or admin UI that originates from a replayed row is
  labeled with its provenance: "replayed, originally collected `source_ts`" vs. "live/synthetic,
  generated `event_ts`" — answering directly whether a displayed number is real-historical or
  invented-live.
- FR-P2. `GET /api/dataset/*` serves the Dataset Explorer: browse/query the original Kaggle CSV
  by device and real timestamp range, independent of Kafka/Spark/Cassandra, reading the same file
  `dataset-init` already fetched (no duplicate ingestion or storage).

**Dashboards (FR-G)**
- FR-G1. Grafana ships pre-provisioned (dashboards, data sources, and alert rules as code
  in the repo, loaded automatically at startup — no manual dashboard or alert building).
- FR-G2. Dashboards implement the KPI catalogue of §9.
- FR-G3. Grafana uses its built-in authentication; default credentials must be changed at
  first login.
- FR-G4. Alert rules (consumer lag, Cassandra write latency, elevated per-service ERROR
  log rate, service down, **disk-usage-critical, D40**) are provisioned as code and route
  to a webhook contact point into the backend (D31, §4.2).

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
- **NFR-4 Retention.** Keep everything by default — no TTL, no automatic deletion. Consequence:
  disk usage grows unboundedly; disk-growth monitoring (KPI-4) and the minimum disk of
  NFR-3 are therefore mandatory, and Risk R-1 applies. The sole sanctioned exception is
  D40's archive-and-trim action (FR-A): explicit, admin-triggered, logged, and lossless
  only in the sense that the data survives in the exported archive file, not in Cassandra.
- **NFR-14 Archive storage (D40).** The archive-and-trim action (FR-A1) writes to a
  dedicated named volume (`archive_data`), one file per invocation, plain newline-delimited
  JSON (matches the event schema, §5.2) so an archived file is re-inspectable without special
  tooling. Not retained under any TTL itself — same "keep everything" default as live data,
  just moved off the Cassandra write/read path — and out of scope for automatic re-import in
  Phase 1 (a later phase could add "restore from archive").
- **NFR-15 Docker socket privilege (D42, superseded by D43/NFR-16).** FR-N2 originally mounted
  `/var/run/docker.sock` into the backend container so it could create/start a new Cassandra container
  via the Docker Engine API — a deliberate, documented exception to this project's otherwise
  minimal-attack-surface stance (NFR-6, NFR-10.1, NFR-11): whoever could reach the admin-gated
  node-deploy endpoint effectively gained host-level container-spawning capability. This prediction
  from D42 held exactly as written: "not the pattern the production Contabo/k3s deployment (P6) would
  use... P6 should replace this mechanism rather than carry it forward" — D43 does that replacement,
  for local dev too, not just production. Kept here for history; NFR-16 is the current mechanism.
- **NFR-16 Kubernetes RBAC, replacing the Docker socket (D43).** The backend's `serviceAccountName`
  (§4.4) is bound to one namespaced Role, not a ClusterRole: `get`/`list`/`watch` on `pods` and
  `statefulsets` (FR-K1, FR-N3), `patch` on the `cassandra` StatefulSet's `/scale` subresource only
  (`resourceNames: ["cassandra"]` — not "any StatefulSet", FR-N2), and `create` on `pods/exec` for
  `nodetool status` polling (FR-N1). No host-level privilege, no privilege beyond what these four
  endpoints actually need, and — unlike NFR-15 — this *is* the pattern the production k3s deployment
  (P6) carries forward unchanged, since it's the same manifests either way (§4.4).
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
  guide, endurance-run procedure, and how to reset all data. Per D41, the docs site also
  carries a concrete, narrative scenario per role (specific actions taken and readings
  encountered, e.g. UC-10/UC-11 walked through end to end) — not just the one-line
  success criteria already in §6's use-case list.
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
| KPI-6 | Infra observability (admin role, D30/D31) | log volume and ERROR rate by service, count of currently-firing alerts by severity, **disk-usage-critical firing state (D40)** | Loki (log queries) + the backend's alert store |

Note: atmospheric-pressure KPIs are computed from the simulated `pressure` field (D23)
and labeled as synthetic in the dashboards.

Note: KPI-4's disk-usage panel now also drives the disk-usage-critical alert rule (FR-G4, D40); its
threshold is calibrated the same way as the endurance-run acceptance threshold in §10 — a percentage
of the sized volume (NFR-3/NFR-12), not a fixed absolute value, so it stays meaningful in both local
and Contabo deployments.

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
| D35 | Out-of-range log, and a fifth "month" resolution | D34 argued a text log couldn't show *how long/how often* a metric was bad — still true, and the charts stay for that. But planners reviewing specific business-relevant readings (temperature, CO, LPG, humidity, ...) also need *which exact reading, when, by how much* — a question a shaded chart region answers only visually, not as a checkable number. Added `BoundaryLog.tsx` below the charts: same per-metric selector, its own independent minute/hour/day/week/month scope, newest-first, one line per breach with the actual min/max value (not the window average — a window can be flagged from a single spike its own average would smooth away) against the normal band or ceiling it crossed. Reuses the exact same `GET /api/sensors/{id}/timeline` data already fetched for the charts, no separate endpoint. "Month" was added to that same endpoint (`environment.py`'s `_rollup_bucket_key`/`rollup_metric_windows`, keyed off the 1st of the calendar month) because a log a planner checks periodically needs a coarser lens than "week" to be useful, not because the charts needed a fifth panel — the charts gained one anyway, for free, since both read the same granularity list |
| D36 | Admin "Docs" tab (superseded by D37, kept for history) | First version: a subset of the project's own `.md` documentation was bundled into the backend image and rendered client-side as HTML with `marked`. Superseded by D37's single local docs site — the multi-page-markdown-plus-renderer approach didn't scale past a handful of short files, and this project already had a much richer interactive doc (the original `containers.html`) sitting outside that system entirely, an inconsistency D37 resolves. |
| D37 | Centralized local docs site, replacing the scattered `docs/*.md` files | The project had accumulated five separate `docs/*.md` files (`ARCHITECTURE.md`, `PROJECT_STRUCTURE.md`, `DEPLOYMENT.md`, `PROGRESS.md`, `TROUBLESHOOTING.md`) plus, alongside them, one much richer interactive HTML doc (`containers.html`, D-numbered informally before this entry) — two different documentation systems for one project, and the plain-markdown ones constantly cross-referenced each other by hand (e.g. `docs/TROUBLESHOOTING.md` P5 §1-style links), which drifts the moment a file is renamed. Consolidated into one local, multi-page site under `docs/`: `index.html` (hub), `containers.html` (kept — architecture + the animated D3 diagrams, unchanged in substance), `deployment.html` (from `DEPLOYMENT.md`), `operations.html` (`PROGRESS.md` + `TROUBLESHOOTING.md` merged — both were "why is it built this way" documents that referenced each other constantly; the troubleshooting log's exact phase/issue numbering — P1 §1 … P11 — was preserved as real anchor IDs, not renumbered, so every existing cross-reference in code comments still resolves), and `reference.html` (from `PROJECT_STRUCTURE.md`). A shared `docs/assets/docs.css`/`docs.js` factors out the design system and the sidebar filter/scroll-spy behavior `containers.html` originated, so all five pages render as one product instead of five one-off ones — change the look once, it applies everywhere. Root `README.md` and `REQUIREMENTS.md` deliberately stay outside this site (README as the GitHub-facing entry point, REQUIREMENTS as the formal spec/decision log) and are cross-linked from `docs/index.html` instead of duplicated into it. The admin "Docs" tab (D36) now embeds this site directly via an admin-gated static-file route (`backend/app/routers/docs.py`'s `GET /api/admin/docs-site/{path}`) in an `<iframe>`, rather than fetching and re-rendering markdown — the same files serve both the local `file://` reading experience and the in-app one, one authored place. `marked` was removed from the frontend's dependencies (`npm uninstall marked`) since nothing parses markdown client-side anymore. |
| D38 | Data provenance: `source_ts` + Dataset Explorer | External review couldn't tell whether a displayed reading was live/synthetic or replayed-real, or when a replayed reading was actually collected — a direct consequence of D28 discarding the dataset's original 2020 timestamps for windowing purposes. Rather than reversing D28 (which would break "last N minutes" queries again), a nullable `source_ts` field is added alongside `event_ts`/`ingest_ts` purely for display, and a standalone Dataset Explorer view browses the original CSV on its own real timeline, reading the same file `dataset-init` already fetched — no new ingestion path or duplicated storage. |
| D39 | Historical comparison overlay | External review noted there was no way to compare a current reading against an earlier period (e.g. a week or a year ago). Added a "compare to" overlay on the existing behavior-over-time charts (FR-E3) rather than a separate view, since the comparison is only useful anchored to the metric already being looked at. Resolves the compared period from live/synthetic Cassandra history when it's within the deployment's own running time, and from the Dataset Explorer (D38) when it predates that — chosen over fabricating a full year of live history, which the project's own short running time can't honestly provide. |
| D40 | Disk-full remediation: alert + archive-and-trim | Risk R-1 (disk exhaustion) was flagged High since v1.0 but had no defined repair path beyond a full data-destroying reset, and no dedicated alert — external review asked directly "what happens if a disk goes full, what's the repair way." Rather than relaxing NFR-4's "keep everything" retention policy wholesale, added one narrow, explicit, admin-triggered, logged action (FR-A) that exports the oldest raw-event partitions to a local archive file before dropping them from Cassandra — data survives, just off the live read/write path — plus a disk-usage-critical Grafana alert (extends FR-G4) so the admin has warning before the disk actually fills. This is the one Phase-1 exception to the control-panel deferral (§2): a single-purpose capacity action, not a general start/stop/inject surface. |
| D41 | Per-role scenario narratives in the docs site | External review felt the UC list's one-line success criteria didn't add up to a believable "a real user does X, reads Y, reacts Z" story for either role, despite the UI itself being mature. Rather than inventing new features to compensate, D41 is a documentation-only decision: NFR-9 now requires the docs site to carry a concrete, narrated walkthrough per role (grounded in UC-10/UC-11 among others), separate from and more detailed than the formal use-case list. |
| D42 | Cassandra storage-usage control + admin-triggered node deploy | A follow-up conversation about Kafka/Cassandra storage limits surfaced that Cassandra's own disk usage had no dedicated signal (D40's alert measures the whole host filesystem) and no admin-facing way to add capacity, even though Cassandra's gossip/token-ring design makes "add a node, let the ring rebalance" the standard, well-supported way it scales storage — unlike Kafka, where a new broker needs an explicit partition-reassignment step to help. Chose real automation with live progress (FR-N2, WebSocket-streamed steps) over a copy-paste runbook, per explicit request; this requires Docker socket access (NFR-15, R-9) — the first Phase-1 admin action to need a new host-level privilege rather than only mutating the app's own data (D40's archive-and-trim). Scoped deliberately short of full automation: token ranges rebalance automatically on bootstrap at the existing RF=1 (no `ALTER KEYSPACE` needed), but reclaiming the original node's freed disk (`nodetool cleanup`) stays a documented manual step (FR-N4) rather than an automated data-redistribution side-effect without a human decision point. The storage "limit" itself is an admin-configured budget compared against Cassandra's own `Storage_Load` metric (already scraped, just never displayed), not a kernel-enforced quota — Docker Desktop's WSL2 backend doesn't support per-volume filesystem quotas, confirmed while scoping this decision. Live-testing D42 twice surfaced real host-resource-contention limits (a second full Cassandra JVM OOM-killed on a 7.7 GiB Docker VM) — a genuine finding, not a code defect, that directly motivated D43. |
| D43 | Kubernetes for the whole stack (k3d locally, k3s in production), replacing the Docker socket | D42's Docker-socket exception (NFR-15/R-9) was accepted as scoped and documented, but the follow-up question was obvious: Kubernetes RBAC exists precisely to grant "scale this one StatefulSet, exec into its pods" without host-root-equivalent access — patching around the socket would have been treating the symptom. Rather than a narrow fix, chose the broader, more coherent move: adopt Kubernetes for everything, per explicit request ("include it at every level"), using **k3d** locally because it *is* k3s, the distribution §4.1/D18 already chose for production — one manifest set instead of two unrelated deployment stories, turning P6 from aspirational into something that actually runs now. Cassandra/Kafka become StatefulSets, node-exporter/promtail become DaemonSets (genuinely per-node, not an arbitrary choice), stateless services become Deployments, one-shot setup becomes Jobs, and the three volume-permission-fixing init containers (D40/D42's `*-volume-init` idiom) disappear entirely — `securityContext.fsGroup` does that natively. Deliberately did not add Helm, Operators, autoscaling, or a multi-node local cluster (§4.4) — same "no more machinery than this phase needs" discipline as D19. Docker Compose stays in the repo as historical reference rather than being deleted, since it documents the D1-D42 era accurately and cleanly. |
| D44 | Cassandra horizontal-scale-out (FR-N2) verified end-to-end on real k3s infrastructure — three real bugs found and fixed | D42's original motivation for admin-triggered Cassandra scaling — relieving storage pressure by adding a node — had never actually been confirmed working end-to-end: D42's Docker-socket version OOM-killed a second Cassandra JVM on a 7.7 GiB Docker Desktop VM before it could; D43 verified the Kubernetes replacement structurally on k3d but not this specific scenario. Installed real k3s (not k3d) via `get.k3s.io` on one of the project's actual Contabo VPS (11 GiB) and ran the actual feature: `POST /api/admin/cassandra/nodes` against a live single-node cluster. It failed three times, for three distinct reasons, each fixed: **(1)** `k8s/base/rbac.yaml`'s `pods/exec` rule granted `create` — the documented Kubernetes convention for this subresource — but this real k3s (`v1.36.4+k3s1`) control plane authorizes the Python client's `connect_get_namespaced_pod_exec()` call against `get` instead; `nodetool status`/`exec` calls 403'd until `get` was added alongside `create`. **(2)** The much bigger one: `k8s/base/statefulset-cassandra.yaml` never set `CASSANDRA_SEEDS`. The official image's entrypoint defaults an unset `CASSANDRA_SEEDS` to the pod's own broadcast address, so the scaled-out `cassandra-1` passed its readiness probe and reported `Running`/`Ready` while silently bootstrapping as its own independent single-node cluster — a fresh `system_auth` superuser role, its own Host ID, `nodetool status` on each pod seeing only itself — never joining `cassandra-0`'s ring at all. This would have made the entire feature a silent no-op in production: green pod, zero actual capacity added. Fixed by setting `CASSANDRA_SEEDS: cassandra-0.cassandra.iot-pipeline.svc.cluster.local` on every replica (including `cassandra-0` itself — a node listing itself as a seed is normal). **(3)** Separately, `cassandra_nodes.py`'s `_wait_pod_ready_sync` polls `read_namespaced_pod_status`, which needs the `pods/status` subresource — genuinely distinct from the `pods` `get/list/watch` rule already granted, and not covered by it. Even after (1) and (2) were fixed and the real Kubernetes scale-up and Cassandra bootstrap/ring-join succeeded, `deploy_node()`'s own readiness poll 403'd on every attempt, so the admin-facing feature reported failure over the WebSocket regardless. Fixed by adding an explicit `pods/status` `get` rule. After all three fixes, `POST /api/admin/cassandra/nodes` against a clean single-node cluster completed the full `creating → healthy → joining_ring → done` sequence with no manual intervention: `cassandra-1` bootstrap-streamed real data from `cassandra-0`, both nodes reached `UN` with the ring split ~49/51%, and `GET /api/admin/cassandra/storage` correctly reported both. **Also reconfirmed D42's original resource-contention finding, this time on real hardware, not Docker Desktop:** running the full stack plus a second Cassandra node pushed this 11 GiB VPS's available memory to ~200 MiB, OOM-killing the unrelated `backend` pod and cascading into a `py4j` failure in `spark-job` — both self-recovered via Kubernetes' normal restart handling with no data loss, but it's a concrete NFR-12 node-sizing signal for full P6: a real second Cassandra node has a real memory cost even outside a constrained dev VM. **Operational note, not a product bug** (FR-N2 is scale-up only; D42 explicitly scoped decommissioning out): reducing `cassandra`'s replica count by deleting the pod/PVC directly, without `nodetool removenode` first, leaves the ring believing the removed node still owns half the token range — hit this firsthand resetting between test runs. This is deliberately **not** full P6 in every other respect: one node, not three; no HA etcd; no Traefik ingress/TLS (backend/Grafana exposed the same direct-hostPort way D43 exposes them for local dev); the only hardening applied is an OS firewall (`ufw`: SSH/8000/3000 allowed, everything else denied, closing off k3s's own 6443/10250 ports, both open to the internet by default). |
| D45 | Simulated the UC-12 "approaching storage budget" scenario end-to-end on real k3s, verified a 3-node scale-out for the first time, and fixed a real concurrency bug | D44 validated FR-N2's deploy mechanism by calling it directly against a healthy cluster, but never the full UC-12 story (admin sees a node genuinely approaching budget, then deploys) — nothing had driven `Storage_Load` near `CASSANDRA_NODE_STORAGE_BUDGET_BYTES`, and no kernel-level quota exists to force it (§5.8). Confirmed `CASSANDRA_NODE_STORAGE_BUDGET_BYTES` needs no code change to simulate this: it's a plain env var, read once at backend startup, so temporarily lowering it below a node's real current load reproduces the critical admin-UI state immediately (reverted afterward; the committed 2 GiB default in `k8s/base/config.env` is unchanged). Found and documented a real lag: `nodetool status`'s `Load` only reflects on-disk SSTables, not memtables/commitlog, so it stayed flat at ~95 KiB for several minutes while `spark-job` actively wrote thousands of rows — a manual `nodetool flush` was needed to make real write volume visible. Confirmed FR-N4 is visibly real, not just documented: after a scale-out, the original node can still show over budget (208.8% in this test) since only new writes rebalance automatically — reclaiming existing data needs the documented manual `nodetool cleanup`. Went one node further than D44 by testing cassandra-1→cassandra-2 for the first time: with `spark-worker`/`spark-job`/observability (`grafana`/`loki`/`kafka-ui`/`kafka-exporter`) scaled to 0 first (freeing ~4 GiB on the same 11 GiB VPS), the third node ring-joined cleanly within ~2 minutes (ownership rebalanced to ~35.7%/31.6%/32.7%), no OOM — showing D42/D44's earlier OOM findings were this VPS running everything at once with no headroom, not a hard ceiling on Cassandra node count. While this was running, found a genuine concurrency bug (not a simulation artifact): `state_poller`'s periodic FR-N3 pod-discovery (a plain `list_namespaced_pod` call) intermittently raised `WebSocketBadStatusException`, because `kubernetes.stream.stream()` (used by `_exec_sync` for `nodetool` calls) monkey-patches its target `ApiClient.request` for the call's duration — not thread-safe — and `CassandraNodes` shared one `CoreV1Api`/`ApiClient` between exec-based and plain-REST call sites running on different threads. Fixed with a second, dedicated `CoreV1Api` instance used only for exec calls; verified with 480 concurrent requests against both affected endpoints, 0 errors post-fix. Since FR-N2 has no decommission path, the third node is now a permanent addition to this VPS's steady state: with the full stack and observability scaled back up, available memory dropped to 242 MiB free / 1.6 GiB available — tighter than this VPS's baseline before D45, a concrete data point for NFR-12 node-sizing in full P6 (each Cassandra node added is a standing cost, not a transient one, without a decommission action to remove it). |
| D46 | `k8s/local-up.sh`/`local-down.sh` (the documented local-dev onboarding path, D43) genuinely live-verified for the first time — found and fixed a real `kubectl`/`KUBECONFIG` bug | The script had carried a header comment since D43 admitting it was "fork-authored, not live-verified... not a successful end-to-end run," and this VPS (real k3s installed natively, per D18/D44) had never actually run it. Installed `k3d` and ran it for real. It failed immediately: `kubectl apply` couldn't reach the k3d cluster's API server at all, instead hitting a connection-refused error against `127.0.0.1:6443`. Root cause: on this host, `/usr/local/bin/kubectl` is a symlink to the `k3s` binary itself (k3s's own convenience `k3s kubectl` subcommand) — a common outcome of installing `k3s` via `get.k3s.io`, and therefore likely on any machine that also follows this project's own production-VPS setup (D18). That bundled `kubectl` defaults to `/etc/rancher/k3s/k3s.yaml` and silently ignores the standard `~/.kube/config` convention `k3d cluster create` correctly merges into, unless `KUBECONFIG` is explicitly set — so every `kubectl` call in the script was targeting the wrong (and in this case stopped) native k3s API server instead of the freshly-created k3d cluster, regardless of k3d having worked correctly. Fixed by explicitly `export KUBECONFIG="$(k3d kubeconfig write "$CLUSTER_NAME")"` right after cluster creation/reuse, so the script is correct regardless of which `kubectl` binary ends up on `PATH`. After the fix, verified the full cycle twice: once reusing an existing cluster, and once genuinely from scratch after `local-down.sh` fully destroyed it — both times every pod reached `Running`/`Completed` and both host-exposed services responded correctly (backend `200`, Grafana `302`-to-login). Separately confirmed 3 of the 5 bugs D43's own "live-verified" claim describes (`SPARK_MASTER_PORT` collision, the `Recreate` deadlock fix, `SPARK_LOCAL_IP` via the Downward API) are already correctly baked into the current manifests — they were fixed before that commit landed, not left broken — so only this `KUBECONFIG` issue and the two already-separately-committed fixes (`.env` comment-stripping, Kafka probe `tcpSocket` check) needed addressing here. |
| D47 | `k8s/local-down.sh` left orphaned Docker resources behind on every run — fixed with explicit cleanup | Found live immediately after D46, running `local-down.sh` a second time: `k3d cluster delete` spins up its own `k3d-<name>-tools` helper container to handle volume/network cleanup, but doesn't reliably stop that container before trying to remove the very network/volume it's still attached to — `docker network rm`/`docker volume rm` failed with "has active endpoints"/"volume is in use" (a real ordering bug in k3d v5.9.0 itself, not a leftover from an earlier run: the container was freshly created seconds before by that same delete call). The `noop`-command tools container never exits on its own, so without a fix these accumulate silently on every `local-down.sh` run — the script still printed "Successfully deleted cluster" and exited 0, masking the leftover state. Fixed by force-removing the tools container, network, and volume by name after `k3d cluster delete` returns, each `\|\| true` since a clean k3d run may have already removed them. Verified directly: reproduced the stuck container/network/volume, ran the fixed script, confirmed all three gone via `docker ps`/`network ls`/`volume ls`. |
| D48 | One deploy mechanism for every environment: `k8s/deploy.sh <local\|prod> <check\|up\|update\|status\|down>`; production docs rewritten to the k3s path | D43 promised "one manifest set, two environments," but only local had a script: production was a hand-typed README recipe that omitted steps `local-up.sh` performs (staging the gitignored `k8s/base/generated/`, namespace-before-Secret, stripping `.env` comments, loading images into k3s' own containerd), and `docs/deployment.html` still called `docker compose` the production path although the VPS had run k3s since D44. `deploy.sh` runs the identical steps in both environments and isolates each genuine difference in a commented branch: **cluster ownership** (local creates/destroys a disposable k3d cluster; prod never creates or deletes k3s, only the namespace, because the cluster is long-lived host infrastructure), **image delivery** (`k3d image import` vs `docker save \| k3s ctr images import -`, because k3s keeps images in its own containerd, not Docker's), **kubeconfig** (explicit in both, never ambient - the D46 bug), **validation strictness** (prod rejects placeholder/short secrets, internet-facing), **`down` safety** (prod: typed confirmation, namespace only, since Cassandra's PVCs are the only copy of the data), and **node count** (multi-node refused: images and `local-path` PVCs are single-host; needs the unbuilt production overlay). `local-up.sh`/`local-down.sh` remain as wrappers. Documentation defects found and fixed: (1) the README sent producer-rate/replay-limit settings to `.env`, which Kubernetes reads only for 6 secrets - real settings live in `k8s/base/config.env` (this VPS had `BACKEND_COOKIE_SECURE=true` in `.env`, silently ignored; `deploy.sh` now warns on such drift); (2) "code changes are picked up automatically by `local-up.sh`" was wrong - `:local` images re-imported under the same tag are not a pod-spec change, so `deploy.sh update <service>` (rollout restart) is required in local and prod; (3) the compose section of `deployment.html` claimed `ufw allow` rules "close the gap" left by Docker's iptables rules - they do not, so every compose-published port (Kafka, Cassandra, Prometheus, Spark UIs...) is internet-reachable regardless of ufw; corrected; (4) the deployment guide's backups/updates/monitoring/teardown/reboot sections described Docker volumes and are rewritten for PVCs, `kubectl`, and the trap that `:local` images exist only in the host's containerd (kubelet image GC or `crictl rmi --prune` can remove them). There is deliberately no `set -x` mode (it would print `.env` secrets). **Verification:** `check` (both modes, against the real k3s API), argument handling, validation failure paths and drift warning were run on the production VPS; `up`, `update` and prod `down` reuse the live-verified D46/D47 steps but their new prod branches were **not** run end to end when this was recorded - the first real `prod up` is the verification and should be logged here. **Not built (stated, not hidden):** TLS/ingress, multi-node, image registry, automated backups, a rehearsed restore; the intended home is a `k8s/overlays/prod` Kustomize overlay applied by `deploy.sh prod`. |
| D49 | Harden `spark_job` and `backend` against real outage/load conditions (commit `6e0f87b`; recorded retroactively) | Two production failures, each fixed at the root. **(1) A poisoned Kafka message crash-looped the whole pipeline:** one message that failed JSON parsing, or parsed but lacked `event_id`/`device_id`/`event_ts`/`ingest_ts`, reached `applyInPandasWithState` and crashed all three streaming queries with an Arrow null-timestamp error - and because the checkpoint always resumed at the same offset, it never self-healed. `spark_job/spark_job/schema.py` now drops such messages before they reach the stateful stage. **(2) The backend was OOM-killed by the historical-comparison toggle:** it fires up to three Dataset Explorer queries concurrently (day/week/month) and each re-scanned the whole Kaggle CSV from disk; three simultaneous full scans exceeded the pod's memory under real pressure. `backend/app/dataset_reader.py` now parses the CSV once and caches it; the backend memory limit was raised 384Mi -> 512Mi (`k8s/base/deployment-backend.yaml`) for headroom around the cache. *Recorded retroactively: this row is written from the commit message; the author reported live verification, which was not re-checked when it was recorded. Note dropped messages are discarded silently - there is no dead-letter topic, so a producer emitting bad events would lose them without an alert.* |
| D50 | Resize `k8s/base` memory limits to fit the 11 GB production node (commit `908c1dd`; recorded retroactively) | The sum of container memory limits was ~12.4 GiB across the 14 steady-state workloads - already over the 11 GB VPS before OS/k3s/containerd overhead, consistent with D44/D45's finding that the full stack left only ~200 MiB-1.6 GiB free. Limits for the peripheral services (grafana, prometheus, loki, kafka-exporter, producer, node-exporter, promtail) were trimmed to observed `kubectl top` usage plus margin, and spark-job (driver) and spark-master moderately; the four components tied to real OOM/stall incidents (cassandra, kafka, spark-worker, backend) were deliberately left alone. **`kafka-ui` is now scaled to 0 replicas by default** (a pure debugging convenience: not host-exposed, not referenced by any FR/UC or the backend health grid) - run `kubectl -n iot-pipeline scale deployment kafka-ui --replicas=1` to browse topics, and note that re-running `deploy.sh up` puts it back to 0. spark-master's smaller limit also required setting `SPARK_DAEMON_MEMORY` explicitly, because Spark daemons default to a 1g heap regardless of the container limit and would otherwise self-OOM on start. New totals per the commit: ~9.6 GiB limits (was ~12.4), ~4.8 GiB requests (was ~6.2), real usage ~5.5 GiB. *Recorded retroactively from the commit message; not re-verified. Consequence to keep in mind: ~1.4 GiB of headroom between limits and the host, so anything that adds a pod, raises a limit or scales Cassandra must re-check `kubectl top nodes` first.* |
| D51 | Cassandra node-deploy notice reworded from "demo/illustration only" to a plain real-action warning (wording only; recorded before commit, author of the working-tree edit not identified) | The notice above FR-N2's "Deploy new Cassandra node" button still carried D42-era wording calling the action a demo that is "not a safe production practice." Since D43/NFR-16 it drives a real, narrowly-scoped Kubernetes scale-up, verified end-to-end in D44/D45: a real pod, a real 5 GiB PVC (`statefulset-cassandra.yaml` volumeClaimTemplate), a real ring join, and no matching remove-node action (§4.3 point 4, scale-up only). Calling that a demo undersold a standing resource commitment on an 11 GiB node where D50 leaves ~1.4 GiB of headroom. The notice now says it is a real action, names the 5 GiB volume, says removal is a manual operator step outside the UI, and asks the admin to check available memory first. CSS class `.demo-only-notice` renamed to `.cassandra-deploy-warning` (no other users). No backend, RBAC or manifest change. **Verified:** the 5 GiB and scale-up-only claims were checked against `k8s/base` and §4.3; `kubectl kustomize k8s/base` and `bash -n k8s/deploy.sh` pass. **Not verified:** the frontend was not built (`npm run build`/type-check not run) and the change is not deployed; production shows the old text until `deploy.sh prod update backend`. |

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
  minimum disk, KPI-4 growth-rate panel with projection, a disk-usage-critical alert
  (D40, FR-G4) firing before the disk actually fills, and the archive-and-trim admin
  action (D40, FR-A) as a repair path that frees space without a full destructive reset
  — the reset procedure remains available as a last resort.
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
  `docs/operations.html#p8-1`. Residual risk: this was one local run, not a
  multi-day soak — the endurance run (§10) will be the real stress test.
- **R-8 — Public OpenStreetMap tile server fair-use limits (Low, local/demo scope).**
  The planner map (D32) fetches tiles directly from `tile.openstreetmap.org`, which has
  a documented fair-use policy not meant for sustained high-traffic production use.
  Confirmed working for local development and demonstration (live-verified: real map
  tiles of Lingen (Ems) rendered correctly with status-colored pins). A future cloud
  deployment (P6-adjacent) serving real public traffic should switch to a paid tile
  provider or a self-hosted tile cache before going live.
- **R-9 — Docker socket exposure via FR-N2 (RESOLVED by D43, live-verified, kept for history).** Mounting
  `/var/run/docker.sock` into the backend (NFR-15) meant anything that compromised the backend process
  gained host-level container control, not just app-level access — a materially larger blast radius
  than any other admin action in this project. D42 accepted this for local-development/educational use
  only, explicitly flagged as not the mechanism production should carry forward. D43 resolves it
  outright rather than continuing to accept it: the backend now holds a namespaced Kubernetes RBAC
  Role (NFR-16) scoped to exactly the four operations FR-N1-N4/FR-K1 need, with no host-level privilege
  at all — and this *is* the production mechanism too, not a local-only exception.

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
   verify cluster behavior (replication visible, single-node failure demo). P11 (below) now
   supplies the base manifests this phase applies — P6's own remaining scope is the real
   infrastructure work (provisioning, hardening, the production Kustomize overlay), not
   writing the manifests themselves.
7. **P7 — Endurance:** rehearsal run, tuning, full 48-hour run on the VPS cluster
   against §10 criteria.
8. **P8 — Role-based redirect (v2.0):** R0 replay-timestamp fix (D28);
   R1 role-based auth + `device_metadata`/`device_thresholds` + `/api/sensors` (D29,
   D33); R2 Leaflet map for the planner role (D32); R3 Loki + Promtail for the admin
   role's centralized logs (D30); R4 Grafana alerting + webhook + admin Alerts tab with
   Explore drill-down (D31); R5 this requirements rewrite. Risks R-7/R-8 flag what's not
   yet live-verified.
9. **P9 — External-feedback response (v2.1):** R6 `source_ts` schema
   addition + Dataset Explorer API/view (D38); R7 historical-comparison overlay on the
   behavior-over-time charts, spanning live history and the Dataset Explorer (D39); R8
   disk-usage-critical alert + archive-and-trim admin action (D40, FR-A); R9 per-role
   scenario narratives added to the docs site (D41).
10. **P10 — Cassandra storage capacity control (v2.2):** R10 `Storage_Load`-based
    per-node usage display (FR-N1); R11 Docker-socket-backed admin node-deploy action with
    WebSocket-streamed step progress (FR-N2, NFR-15); R12 dynamic `cassandra-*` discovery in the
    Deployment step's health grid (FR-N3, FR-W1).
11. **P11 — Kubernetes migration, local + shared manifests (this document's v3.0):** R13 base
    Kubernetes manifests for every service (StatefulSets, Deployments, DaemonSets, Jobs, §4.4's
    mapping table) plus k3d as the local runtime; R14 RBAC ServiceAccount/Role replacing the Docker
    socket (NFR-16); R15 FR-N1-N4 reimplemented against the Kubernetes API; R16 the new admin
    Kubernetes-status panel (FR-K1, UC-13). This is a large step toward P6 (below) but not P6 itself:
    P6's remaining scope after P11 is narrower — provisioning and hardening the actual three Contabo
    VPS and applying these same manifests there via a production Kustomize overlay (3-node topology,
    Traefik ingress, TLS, NFR-11's firewall rules) — real infrastructure work, not manifest-writing.

Each phase should end in a runnable, demonstrable state.
