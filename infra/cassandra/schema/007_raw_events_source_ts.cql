-- Migration for deployments created before D38: 002_raw_events.cql's CREATE TABLE IF
-- NOT EXISTS is a no-op against an already-existing table, so the source_ts column
-- added there needs a separate ALTER TABLE here to reach an existing keyspace. Safe to
-- run every startup (cassandra-schema-init runs every file unconditionally on every
-- `docker compose up`) since Cassandra 4.1's ADD IF NOT EXISTS ignores an already-present
-- column instead of erroring - verified against the CQL grammar for this image
-- (cassandra:4.1.12, see docker-compose.yml), not live-tested against a running cluster.
ALTER TABLE iot.raw_events ADD IF NOT EXISTS source_ts timestamp;
