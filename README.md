# iu_project_data_engineering
Project: Data Engineering for IU Akademie

A role-based environmental sensor platform for the municipality of Lingen (Ems) — Kafka →
Spark Structured Streaming → Cassandra underneath, with two web app roles on top: an
**environmental/planner** role (a live sensor map, air quality scoring, behavior-over-time
charts, and an out-of-range log) and an **infrastructure/admin** role (the pipeline health
tour, centralized logs, Grafana-fired alerts with log drill-down) — plus a Grafana KPI
dashboard, all running end to end from one `./k8s/local-up.sh` (a local Kubernetes/k3d
cluster) or, still supported as a legacy fallback, one `docker compose up -d`. See
`REQUIREMENTS.md` for the full project scope and phase roadmap, and **`docs/index.html`**
for everything else — open it directly in a browser (no server needed) for the full
documentation site: how the system is built (every module explained, animated
data-flow/boot-order diagrams, a per-container reference), how to deploy it on a public
VPS, current status and non-obvious bugs/gotchas found while building and operating the
stack, and a file-by-file reference for the whole repo.

## Prerequisites

- Docker Desktop (WSL2 backend on Windows) or Docker Engine on Linux.
- [k3d](https://k3d.io/) (k3s-in-Docker) and `kubectl` — the primary local runtime as of
  `REQUIREMENTS.md` D43. `docker compose` (Compose v2) still works as a legacy fallback,
  see [Legacy: docker compose](#legacy-docker-compose) below.
- ~16 GB RAM / 4 CPU cores free, ~25 GB free disk for normal use (see
  `REQUIREMENTS.md` NFR-3 for the 48-hour endurance-run sizing).
- Internet access on first start, so the `dataset-init` job can fetch the
  Kaggle source dataset — see [Dataset](#dataset) below. No manual download step.

## Quick start

```
cp .env.example .env
# edit .env: set real values for GRAFANA_ADMIN_PASSWORD, BACKEND_ADMIN_PASSWORD,
# BACKEND_PLANNER_PASSWORD, and BACKEND_SESSION_SECRET (e.g. `openssl rand -hex 32`
# for the last one)

./k8s/local-up.sh
```

First start creates a local k3d cluster, builds the custom images, imports them into
that cluster, generates a Kubernetes `Secret` from `.env` (never committed — same rule as
`.env` itself), and applies the full manifest set (`k8s/base`, a plain Kustomize
directory — no Helm). This takes several minutes on a cold start (same reasons as before:
pre-warming Spark's dependency cache, fetching the Kaggle dataset). It prints the two
URLs the host can actually reach when it's done: the backend at
**http://localhost:8000** and Grafana at **http://localhost:3000** — see
`REQUIREMENTS.md` §4.4 for why nothing else (Spark UIs, kafka-ui, Prometheus, ...) is
exposed to the host anymore; use `kubectl -n iot-pipeline port-forward` for those during
development. This path is live-verified end to end (see `docs/operations.html`'s D43
section for the real bugs a live cluster surfaced and fixed) — see that section if
anything looks different.

Tear down (deletes the whole local cluster, including its data — the k3d equivalent of
`docker compose down -v`):
```
./k8s/local-down.sh
```

### Legacy: docker compose

`docker-compose.yml` is kept as a historical reference (`REQUIREMENTS.md` D43) — it still
runs the full stack on its own, but no longer holds a Docker-socket-mounted backend the
way it briefly did under D42; that control now only works under the k3d/Kubernetes path.

```
docker compose up -d --build --wait
```

`--wait` blocks until every service with a healthcheck reports `healthy` — check with
`docker compose ps` if it times out or exits non-zero; every long-running service should
reach `healthy`, and the `*-init`/`*-schema-init` one-shot containers should show
`Exited (0)` (that's success).

If you ever rebuild or restart just one service by name (`docker compose up -d --build
backend`, say), Compose only reconciles that service — anything else that had drifted to
`Exited` (e.g. after a host sleep/resume, a Docker Desktop restart, or a sibling service
crash-looping out) stays dead until something names it again. Run a bare `docker compose
up -d --wait` (no service argument) afterward to sweep the whole stack back to its
desired state — see `docs/operations.html#p9` for a real incident this caused.

Stop (keeps all data):
```
docker compose down
```

Reset everything (drops all named volumes — irreversible):
```
docker compose down -v
```

## Walkthrough guide

Once the stack is healthy, open **http://localhost:8000** and log in with one of the two
role accounts from `.env` — the same login form serves both roles, which one you land on
depends on which account you use.

### Environmental/planner role (`BACKEND_PLANNER_USERNAME`/`BACKEND_PLANNER_PASSWORD`)

A live map of Lingen (Ems) with one pin per sensor, colored by current status
(ok/warning/critical). Click a pin to see its latest reading, air quality score, comfort
index, and its chronic-exposure rate, plus two ways to review a selected metric's
history: five behavior-over-time charts (minute/hour/day/week/month) with shaded regions
over any span that fell outside the acceptable range, and below them an out-of-range log
listing the specific breaching readings in plain language — newest first, independently
scoped at the same five resolutions. This is the surface that actually answers "is it
safe here, and is it a persistent problem or a one-off" (`REQUIREMENTS.md` UC-8).

### Infrastructure/admin role (`BACKEND_ADMIN_USERNAME`/`BACKEND_ADMIN_PASSWORD`)

**Pipeline tab** — the guided pipeline tour in six steps, all showing live data with
WebSocket updates:

1. **Deployment** — a health grid of every service in the stack.
2. **Ingestion** — the producer's current mode (replaying the dataset vs. generating
   synthetic data), throughput, and a sample of recent events.
3. **Kafka** — live broker offsets and per-query consumer lag.
4. **Spark** — the three streaming queries' batch progress and end-to-end latency.
5. **Cassandra** — the most recently written rows.
6. **Summary** — totals, and a link into Grafana for historical trends.

**Alerts tab** — a live feed of Grafana-fired alerts (consumer lag, Cassandra write
latency, elevated per-service error rate, service down), each with a one-click link into
Grafana Explore, pre-scoped to that alert's service and a recent time window
(`REQUIREMENTS.md` UC-9).

**Kubernetes tab** — pod and StatefulSet/Deployment health read straight from the
Kubernetes API (`REQUIREMENTS.md` FR-K1, D43), via the same narrowly-scoped RBAC Role the
Cassandra node-deploy control uses. Shows `503`/unavailable when running under the legacy
`docker compose` path instead, since there's no cluster to ask.

**Docs tab** — the full local documentation site (`docs/index.html` and everything it
links to), embedded in-app so an administrator can read how the system was conceived and
built without a repo checkout on the host — the exact same pages a developer opens
directly via `file://`, one authored place. `REQUIREMENTS.md` and this README stay
repository-only, cross-linked from the docs site instead of duplicated into it — see
`REQUIREMENTS.md` D37.

Watch for the **hand-over** (`REQUIREMENTS.md` UC-3): the producer replays the full
Kaggle dataset (~67 minutes at the default 100 msg/s) before switching to synthetic
generation — the Ingestion step's mode badge flips from `REPLAY` to `SYNTHETIC` when it
happens. To see this sooner during a demo, set `PRODUCER_REPLAY_ROW_LIMIT` (e.g. `2000`)
in `.env` before starting — this replays only the last N rows instead of the whole file.

Grafana (**http://localhost:3000**, credentials from `.env`) has the full KPI
dashboard (`REQUIREMENTS.md` §9: throughput/lag, latency, business aggregates, disk
growth, anomaly drill-down, and now logs) auto-provisioned — no manual setup needed.

## Endurance-run procedure

`REQUIREMENTS.md` §10 defines the acceptance run: 500 msg/s sustained for 48 hours with
no service failure. To run it:

1. Ensure the host meets the endurance sizing in `REQUIREMENTS.md` NFR-3
   (100 GB free disk minimum — retention has no TTL, so usage grows for the whole run).
2. Set `PRODUCER_RATE_MSGS_PER_SEC=500` in `.env` before starting (or restart the
   `producer` service after changing it).
3. Start the stack fresh so the 48-hour window starts from a clean baseline: either
   `./k8s/local-down.sh && ./k8s/local-up.sh` (k3d) or `docker compose down -v && docker
   compose up -d --build` (legacy).
4. Watch Grafana throughout — KPI-1 (lag), KPI-2 (latency), and KPI-4 (disk growth) are
   the ones most likely to reveal a problem before it becomes a failure.
5. At the 48-hour mark, check the acceptance criteria in `REQUIREMENTS.md` §10 (no
   restarts, no sustained lag growth, disk within the sized budget, latency within
   NFR-1/NFR-2's bounds).

## Dataset

The Kaggle source dataset (§5.1 of `REQUIREMENTS.md`, `garystafford/environmental-sensor-data-132k`)
is not committed to the repo — it's ~62 MB and public. Both `./k8s/local-up.sh` and
`docker compose up -d` fetch it automatically via the one-shot `dataset-init`
service/Job (same pattern as `kafka-topic-init`/`cassandra-schema-init`): it downloads
into a `kaggle_dataset` volume/PVC that `producer`, `spark-job`, and `spark-worker` all
mount read-only, and skips the download entirely on future restarts once the volume
already has the file.

The dataset is public, so this needs **no credentials** in the common case. If Kaggle
ever requires auth for it, set `KAGGLE_USERNAME`/`KAGGLE_KEY` in `.env` (from
https://www.kaggle.com/settings → API → Create New Token) — never commit those values.

To run the fetch by hand outside Docker (e.g. to inspect the CSV locally), see
`kaggle_repository/download_repository.py` — it takes the same env vars and writes to
`./kaggle_repository` by default.

## Deploying for real users

For putting this on a public VPS instead of running it locally — server hardening,
firewall rules, TLS, backups, and updates — see `docs/deployment.html`. That guide is
still `docker compose`-based, not the k3d path above: it documents the interim
single-VPS deployment that's actually been exercised on a real machine, not the
3-VPS k3s production target (`REQUIREMENTS.md` §4.1, "full P6"), which D43's local k3d
work is a real step toward but hasn't reached yet — see `docs/operations.html`'s
"Where to pick this up next" for exactly what's still missing.
