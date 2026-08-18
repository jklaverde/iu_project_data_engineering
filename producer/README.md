# Producer (P2 — ingestion)

Replays the Kaggle sensor dataset to Kafka, then hands over to a synthetic
generator when the dataset is exhausted (REQUIREMENTS.md §5, FR-I). See the
root `README.md` for the full-stack quick start — normally this runs as the
`producer` service in `docker-compose.yml` and needs no standalone setup.

## Running standalone (outside Docker)

```
pip install -r requirements.txt
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_TOPIC_NAME=sensor-readings
export PRODUCER_DATASET_CSV_PATH=../kaggle_repository/iot_telemetry_data.csv
python -m producer.main
```

## Configuration

All configuration is via environment variables — see `.env.example` at the
repo root for the full list and defaults (`PRODUCER_RATE_MSGS_PER_SEC`,
`PRODUCER_ANOMALY_PROBABILITY`, `PRODUCER_ANOMALY_SIGMA_MULTIPLIER`,
`PRODUCER_DATASET_CSV_PATH`, `PRODUCER_REPLAY_ROW_LIMIT`, `PRODUCER_STATE_PORT`,
`PRODUCER_LOG_LEVEL`).

`PRODUCER_REPLAY_ROW_LIMIT` is a development aid: set it to a small number
(e.g. `2000`) to replay only the last N rows of the dataset instead of all
~405K, reaching the synthetic hand-over in seconds instead of ~67 minutes.

## State endpoint

`GET http://localhost:<PRODUCER_STATE_PORT>/state` returns the producer's
current mode, configured rate, event counters, and hand-over timestamp
(FR-I4). `GET /healthz` is used by the compose healthcheck.
