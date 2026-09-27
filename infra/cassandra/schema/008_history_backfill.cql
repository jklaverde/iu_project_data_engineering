-- One row describing the year-long derived history (D52, REQUIREMENTS.md §5.9).
-- Written by the history-backfill Job (backend/app/history_backfill.py):
-- anchor_ts is T0, the hour the derived timeline ends at; history_start is
-- T0 minus span_days. completed_at stays null until every agg_1h row has been
-- written, so a Job that crashed half-way re-runs with the SAME anchor (its
-- writes are idempotent upserts) instead of starting a second, shifted year.
-- The backend reads history_start to decide whether a "compare to" period is
-- covered by Cassandra (routers/sensors.py). Dropping the keyspace drops this
-- row too, so the next backfill picks a fresh anchor.
CREATE TABLE IF NOT EXISTS iot.history_backfill (
    id             text,
    anchor_ts      timestamp,
    history_start  timestamp,
    span_days      int,
    sample_minutes int,
    seed           int,
    rows_written   bigint,
    completed_at   timestamp,
    PRIMARY KEY (id)
);
