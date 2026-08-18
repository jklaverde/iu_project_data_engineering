# iu_project_data_engineering
Project: Data Engineering for IU Akademie

See `REQUIREMENTS.md` for the full project scope, architecture, and phase roadmap, and
`docs/TROUBLESHOOTING.md` for non-obvious bugs and environment gotchas found while
building and operating the stack.

## Quick start (P1 — local infrastructure)

Prerequisites: Docker Desktop (WSL2 backend), Docker Compose v2.

```
cp .env.example .env
# edit .env and set a real GRAFANA_ADMIN_PASSWORD
docker compose up -d
```

Stop (keeps data):

```
docker compose down
```

Reset all data (drops named volumes):

```
docker compose down -v
```

### What you should see
- `docker compose ps` — all services show `healthy` (kafka, cassandra, spark-master,
  spark-worker, prometheus, grafana, kafka-ui); the `kafka-topic-init` and
  `cassandra-schema-init` one-shot containers show `Exited (0)`.
- Kafka topic `sensor-readings` exists with 3 partitions.
- Cassandra keyspace `iot` exists with tables `raw_events`, `agg_1m`, `agg_1h`.
- Spark master UI at http://localhost:8090 lists 1 worker.
- Prometheus UI reachable at http://localhost:9090 (Status → Targets shows itself `UP`).
- Grafana reachable at http://localhost:3000, logs in with the credentials from `.env`.
- kafka-ui reachable at http://localhost:8080 for browsing the topic.

No producer or Spark job runs yet — this is infrastructure only (P1). Ingestion (P2) and
stream processing (P3) come next.

## Dataset

The Kaggle source dataset (§5.1 of `REQUIREMENTS.md`) is not committed to the repo — it's
~62 MB and freely downloadable. Fetch it locally with:

```
python kaggle_repository/download_repository.py
```

This uses `kagglehub` and requires Kaggle API credentials on your machine (either
`~/.kaggle/kaggle.json` or the `KAGGLE_USERNAME`/`KAGGLE_KEY` environment variables) —
never commit those credentials to this repo.
