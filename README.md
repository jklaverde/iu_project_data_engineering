# iu_project_data_engineering
Project: Data Engineering for IU Akademie

A streaming sensor-data pipeline — Kafka → Spark Structured Streaming → Cassandra —
with a guided web app and Grafana dashboards, running end to end from one
`docker compose up -d`. See `REQUIREMENTS.md` for the full project scope and phase
roadmap, `docs/ARCHITECTURE.md` for how the system is built (every module explained,
diagrams, data flow), `docs/DEPLOYMENT.md` for putting this on a public VPS,
`docs/PROGRESS.md` for current status and where to pick this project back up, and
`docs/TROUBLESHOOTING.md` for non-obvious bugs and environment gotchas found while
building and operating the stack.

## Prerequisites

- Docker Desktop (WSL2 backend on Windows) or Docker Engine + Compose v2 on Linux.
- ~16 GB RAM / 4 CPU cores free, ~25 GB free disk for normal use (see
  `REQUIREMENTS.md` NFR-3 for the 48-hour endurance-run sizing).
- Internet access on first start, so the `dataset-init` container can fetch the
  Kaggle source dataset — see [Dataset](#dataset) below. No manual download step.

## Quick start

```
cp .env.example .env
# edit .env: set real values for GRAFANA_ADMIN_PASSWORD, BACKEND_ADMIN_PASSWORD,
# and BACKEND_SESSION_SECRET (e.g. `openssl rand -hex 32` for the last one)

docker compose up -d --build
```

First start builds the custom images, pre-warms Spark's dependency cache, and fetches
the Kaggle dataset into a named volume — this takes several minutes. Watch it come up
with `docker compose ps`: every long-running service should reach `healthy`, and the
`*-init`/`*-schema-init` one-shot containers should show `Exited (0)` (that's success).
See `docs/TROUBLESHOOTING.md` if anything looks different, and `docs/PROGRESS.md`'s
"Resuming locally" section for cold-start timing details (baseline recomputation,
catching up on a Kafka backlog).

Stop (keeps all data):
```
docker compose down
```

Reset everything (drops all named volumes — irreversible):
```
docker compose down -v
```

## Walkthrough guide

Once the stack is healthy, open **http://localhost:8000** and log in with
`BACKEND_ADMIN_USERNAME`/`BACKEND_ADMIN_PASSWORD` from `.env`. The guided web app walks
through the pipeline in six steps, all showing live data with WebSocket updates:

1. **Deployment** — a health grid of every service in the stack.
2. **Ingestion** — the producer's current mode (replaying the dataset vs. generating
   synthetic data), throughput, and a sample of recent events.
3. **Kafka** — live broker offsets and per-query consumer lag.
4. **Spark** — the three streaming queries' batch progress and end-to-end latency.
5. **Cassandra** — the most recently written rows.
6. **Summary** — totals, and a link into Grafana for historical trends.

Watch for the **hand-over** (`REQUIREMENTS.md` UC-3): the producer replays the full
Kaggle dataset (~67 minutes at the default 100 msg/s) before switching to synthetic
generation — the Ingestion step's mode badge flips from `REPLAY` to `SYNTHETIC` when it
happens. To see this sooner during a demo, set `PRODUCER_REPLAY_ROW_LIMIT` (e.g. `2000`)
in `.env` before starting — this replays only the last N rows instead of the whole file.

Grafana (**http://localhost:3000**, credentials from `.env`) has the full KPI
dashboard (`REQUIREMENTS.md` §9: throughput/lag, latency, business aggregates, disk
growth, anomaly drill-down) auto-provisioned — no manual setup needed.

## Endurance-run procedure

`REQUIREMENTS.md` §10 defines the acceptance run: 500 msg/s sustained for 48 hours with
no service failure. To run it:

1. Ensure the host meets the endurance sizing in `REQUIREMENTS.md` NFR-3
   (100 GB free disk minimum — retention has no TTL, so usage grows for the whole run).
2. Set `PRODUCER_RATE_MSGS_PER_SEC=500` in `.env` before starting (or restart the
   `producer` service after changing it).
3. Start the stack fresh (`docker compose down -v && docker compose up -d --build`) so
   the 48-hour window starts from a clean baseline.
4. Watch Grafana throughout — KPI-1 (lag), KPI-2 (latency), and KPI-4 (disk growth) are
   the ones most likely to reveal a problem before it becomes a failure.
5. At the 48-hour mark, check the acceptance criteria in `REQUIREMENTS.md` §10 (no
   restarts, no sustained lag growth, disk within the sized budget, latency within
   NFR-1/NFR-2's bounds).

## Dataset

The Kaggle source dataset (§5.1 of `REQUIREMENTS.md`, `garystafford/environmental-sensor-data-132k`)
is not committed to the repo — it's ~62 MB and public. `docker compose up -d` fetches
it automatically via the one-shot `dataset-init` service (same pattern as
`kafka-topic-init`/`cassandra-schema-init`): it downloads into a named volume
(`kaggle_dataset`) that `producer`, `spark-job`, and `spark-worker` all mount
read-only, and skips the download entirely on future restarts once the volume already
has the file.

The dataset is public, so this needs **no credentials** in the common case. If Kaggle
ever requires auth for it, set `KAGGLE_USERNAME`/`KAGGLE_KEY` in `.env` (from
https://www.kaggle.com/settings → API → Create New Token) — never commit those values.

To run the fetch by hand outside Docker (e.g. to inspect the CSV locally), see
`kaggle_repository/download_repository.py` — it takes the same env vars and writes to
`./kaggle_repository` by default.

## Deploying for real users

For putting this on a public VPS instead of running it locally — server hardening,
firewall rules, TLS, backups, and updates — see `docs/DEPLOYMENT.md`.
