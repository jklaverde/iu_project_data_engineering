# Troubleshooting / Known Issues Log

Running log of non-obvious bugs, gotchas, and environment quirks found while building
and operating this stack — kept so later phases (and future debugging sessions) don't
rediscover the same root causes from scratch. Ordered by phase; append new entries
under the phase that surfaced them.

---

## P1 — Foundation (local docker-compose stack)

### 1. Cassandra crash-loops on boot: `Unable to find snitch class 'GossipPropertyFileSnitch'`

- **Symptom:** `cassandra` container exits immediately (exit code 3) on every start;
  `docker compose logs cassandra` shows `ConfigurationException: Unable to find snitch
  class 'org.apache.cassandra.locator.GossipPropertyFileSnitch'` /
  `ClassNotFoundException`.
- **Cause:** Typo. The real class is `GossipingPropertyFileSnitch` (with "-ing") — there
  is no `GossipPropertyFileSnitch` in Cassandra.
- **Fix:** `CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch` in
  `docker-compose.yml`.

### 2. Kafka data silently does not survive `docker compose down && up -d` (breaks NFR-8)

- **Symptom:** No error at all — the stack looks healthy after every restart. But the
  Kafka topic's `TopicId` (visible via `kafka-topics.sh --describe`) is different every
  time, meaning the whole KRaft cluster (and all topic data) was silently recreated from
  scratch. `kafka-topic-init`'s log says `Created topic sensor-readings.` on *every* run
  instead of only the first.
- **Cause:** The volume was mounted at `/var/lib/kafka/kafka_data`, but the
  `apache/kafka:3.7.0` image's actual KRaft log directory is `/tmp/kafka-logs` — visible
  only in the JVM's own runtime log line
  (`[LogLoader partition=__cluster_metadata-0, dir=/tmp/kafka-logs]`), **not** in
  `/etc/kafka/docker/server.properties`, which looks like the effective config but is
  just a template not read at runtime (the real generated config lives at
  `/opt/kafka/config/server.properties`, and it has no `log.dirs` line, so Kafka's
  hardcoded default of `/tmp/kafka-logs` applied). The mounted volume was therefore
  never actually written to; every restart reformatted a brand-new cluster on ephemeral
  container-local disk.
- **How it was found:** inserted a probe row / recorded a `TopicId`, ran a real
  `docker compose down` + `up -d` cycle, and diffed before/after — config validation
  and "does it start" checks alone do not catch this class of bug.
- **Fix:** two parts —
  1. `KAFKA_LOG_DIRS: /var/lib/kafka/kafka_data` explicitly set in `kafka`'s
     `environment`, so the log directory actually matches the mounted volume.
  2. A new one-shot `kafka-volume-init` service (runs as `root`, `chown -R 1000:1000`
     on the volume, then exits) that `kafka` depends on via
     `condition: service_completed_successfully`. This was needed because a **fresh**
     named Docker volume is mounted root-owned by default when the target path doesn't
     pre-exist with different ownership in the image, but the `apache/kafka` image runs
     as non-root `appuser` (uid 1000) — without the chown step, Kafka fails to start
     with a permission error the moment it tries to write to the now-correctly-targeted
     volume.
- **General lesson:** for any container image, don't trust a config file found via
  `find`/`cat` inside the image to be the *effective* runtime config — some images
  render the real config from a template at container start, or use hardcoded defaults
  when a value isn't explicitly set. Confirm the actual data directory from the
  process's own startup log, and confirm persistence by actually cycling the stack and
  diffing an identifier before/after — not just by checking the container starts.

### 3. Host port collisions are with *other, unrelated* things on this machine, not this project

- **`kafka-ui`'s default host port 8080** collided with an unrelated pre-existing
  process already listening on this dev machine (not part of this project). Worked
  around by remapping `KAFKA_UI_PORT=8082` in the local, gitignored `.env` — deliberately
  **not** changed in `.env.example`, since 8080 is kafka-ui's conventional default and
  the collision is specific to this machine, not the project.
- **Container name collisions:** stopped, unrelated leftover containers already existed
  on this machine named `kafka` / `kafka-ui` (orphaned from the old, now-deleted
  `pub_sub/docker-compose.yml`) and `spark-master` (from a completely unrelated old
  project). Fixed at the project level, not by touching those containers: added
  `name: iu-sensor-pipeline` at the top of `docker-compose.yml` and removed every
  explicit `container_name:` override, so Compose namespaces all containers as
  `iu-sensor-pipeline-<service>-1` and can't collide with anything else on the host,
  now or in future phases.
- **Lesson:** don't hardcode `container_name:` in a compose file meant to run on a
  shared dev machine with many other projects — let Compose's project-prefixed default
  naming do its job.

---

## P3 — Processing (PySpark Structured Streaming job)

The unifying theme of every bug below: **this is a real distributed cluster** (a
`spark-job` driver container plus a separate `spark-worker` executor container), not a
single-process local Spark session. Anything that "obviously" only needs to exist on
the driver — a mounted file, a checkpoint directory, an installed Python package, an
importable module — can silently fail on the executor instead, often with no error
until a task actually runs there. Every fix below is a variant of "make sure executors
have it too, not just the driver."

### 4. Batch CSV read fails on the executor: `File file:/data/iot_telemetry_data.csv does not exist`

- **Symptom:** the job's one-time baseline-seed read
  (`spark.read.csv(SPARK_JOB_BASELINE_CSV_PATH)`) fails with
  `SparkFileNotFoundException`, reported by a task running on the **worker's** IP, not
  the driver.
- **Cause:** `spark.read.csv(...)` is a distributed batch read — Spark schedules the
  actual read task on an **executor** (`spark-worker`), not the driver (`spark-job`).
  Only `spark-job`'s `docker-compose.yml` service had `./kaggle_repository:/data:ro`
  mounted.
- **Fix:** mount the same volume into `spark-worker` too.
- **General lesson:** any local file path a Spark job reads or writes must be mounted
  identically on every node that can run a task for that job, not just the driver —
  true even for a single-worker "cluster."

### 5. Checkpoint `mkdir` fails for state-store paths, on top of the already-expected volume-permission issue

- **Symptom:** `java.io.IOException: mkdir of file:/opt/spark-checkpoints/agg_1m/state/1/0/_metadata failed`
  (and similarly for `raw_events`, `agg_1h`).
- **Cause:** two layered issues. First, the generic one already known from P1 #2's
  lesson: a fresh named Docker volume mounts root-owned, breaking writes from the
  image's non-root user (confirmed `apache/spark:3.5.9` runs as `spark`, uid 185, via
  `docker run --rm apache/spark:3.5.9 id`) — fixed with a `spark-job-volume-init`
  one-shot `chown -R 185:185`, same pattern as `kafka-volume-init`. Second, and less
  obvious: Structured Streaming's **state-store data** (for `applyInPandasWithState`
  and windowed aggregations) is written by **executors**, not the driver — so even
  after fixing permissions, `spark_checkpoints` still needed to be mounted into
  `spark-worker`, not just `spark-job`.
- **Fix:** mount `spark_checkpoints` into both `spark-job` and `spark-worker`; chown via
  `spark-job-volume-init` before either starts.

### 6. `ModuleNotFoundError: No module named 'pandas'` / `'pyarrow'` on the executor

- **Symptom:** the driver starts fine (imports work there), but the first micro-batch
  that actually runs the `applyInPandasWithState` function fails on the executor with
  `ModuleNotFoundError`, deep in PySpark's own Arrow serialization code.
- **Cause:** `applyInPandasWithState` is a pandas UDF under the hood — it needs
  `pandas`/`pyarrow` installed wherever the UDF actually executes, which is the
  **executor**, not the driver. The base `apache/spark:3.5.9` image ships neither.
  `spark_job/Dockerfile` correctly pip-installs both, but `spark-worker` was still using
  the plain upstream image.
- **Fix:** a new `spark_job/worker.Dockerfile` (base image + the same
  `requirements.txt`), and `spark-worker` in `docker-compose.yml` switched from a
  pulled `image:` to a `build:` using it.
- **General lesson:** PySpark auto-distributes `--packages` JARs to executors, but does
  **not** auto-distribute pip-installed Python packages — those need to be baked into
  whatever image the executors actually run.

### 7. `ModuleNotFoundError: No module named 'spark_job'` on the executor, when unpickling a closure

- **Symptom:** different from #6 — this is the job's *own* package, not a third-party
  one, failing to import on the executor while deserializing the
  `applyInPandasWithState` function via `cloudpickle.loads`.
- **Cause:** a wrong assumption going in was that cloudpickle always serializes a
  function fully "by value," so only the driver needs the defining package importable.
  Not true: cloudpickle pickles functions defined in an **importable module** (as
  opposed to `__main__`, or a truly dynamically-constructed function) **by reference** —
  it stores the module/qualname and expects the receiving side to `import` it, the same
  as plain `pickle` would for a top-level function. Since `spark_job` was never shipped
  to the executor (only the driver container has it copied in), unpickling fails there.
- **Fix:** zip the `spark_job/` package at Docker build time
  (`shutil.make_archive('/opt/app/spark_job', 'zip', '/opt/app', 'spark_job')`) and add
  `--py-files /opt/app/spark_job.zip` to the `spark-submit` command in
  `entrypoint.sh`.
- **General lesson:** don't assume PySpark UDF closures are executor-independent just
  because they're passed as plain Python callables — if the function lives in a real
  package (not `__main__`), ship that package via `--py-files` regardless.

### 8. Cassandra connector rejects a write with columns the target table doesn't have

- **Symptom:** `java.util.NoSuchElementException: Columns not found in table
  iot.agg_1h: write_ts` (and the same for `agg_1m`) — the connector aborts the write
  outright rather than silently dropping the unrecognized column.
- **Cause:** the shared `foreachBatch` writer helper
  (`cassandra_sink.make_foreach_batch_writer`) unconditionally added a `write_ts`
  column to every DataFrame it wrote, but only `iot.raw_events` actually has that
  column in its CQL schema — `agg_1m`/`agg_1h` don't (a window's aggregate has no
  single meaningful "row write time" the way one event does).
- **Fix:** made `stamp_write_ts` a parameter of the writer factory, `True` only for the
  `raw_events` query.
- **General lesson:** a generic "one writer for every table" helper is a trap the
  moment the tables' schemas actually differ — verify against each target table's real
  column list rather than assuming a shared enrichment step is harmless everywhere it's
  reused.

### General P3 lesson

All five bugs above were caught by actually running the job against the live stack —
including, usefully, a stack that already had ~9 hours (~500K messages) of real
producer traffic queued in Kafka, which turned "does it start" into "does it correctly
process a real backlog and recover from a restart." None of these would have surfaced
from a syntax check, a `spark-submit --deploy-mode client` dry run against `local[*]`,
or code review alone — they are all specifically about the driver/executor split in a
genuine (if small) cluster.

---

## P4 — Observability (Prometheus exporters, Grafana dashboards)

### 9. `node-exporter`'s recommended `/:/host:ro,rslave` mount fails on Docker Desktop

- **Symptom:** `docker compose up` fails immediately with `path / is mounted on / but
  it is not a shared or slave mount`.
- **Cause:** `rslave` mount propagation (common in node-exporter docker-compose
  examples written for native Linux hosts) needs the source mount to already be a
  shared/slave mount — not guaranteed by Docker Desktop's Linux VM on Windows.
- **Fix:** drop the propagation flag, mount as plain `/:/host:ro`. Still gives real
  filesystem metrics for whatever the Docker Desktop VM sees as `/` (see #12 below for
  the scoping caveat that comes with that).

### 10. Cassandra's base image can't download over HTTPS at build time: `curl: (77) error setting certificate file`

- **Symptom:** `RUN curl -fsSL ... jmx_prometheus_javaagent.jar` fails during
  `docker build`, even after installing `curl` (fixes a prior `curl: not found`).
- **Cause:** the base `cassandra:4.1.12` image has neither `curl` nor
  `ca-certificates` installed. `curl` alone isn't enough for an HTTPS URL — without a
  CA bundle it can't verify any TLS certificate.
- **Fix:** `apt-get install -y curl ca-certificates` together, not just `curl`.

### 11. Modern Grafana images don't have `grafana-cli`

- **Symptom:** `RUN grafana-cli --pluginsDir ... plugins install ...` fails with
  `grafana-cli: not found`.
- **Cause:** Grafana consolidated its CLI into the main `grafana` binary — the command
  is `grafana cli ...` (a subcommand), not a separate `grafana-cli` executable.
  Confirmed by actually running `grafana --help` inside the image rather than assuming
  the old command still works.
- **Fix:** `grafana cli --pluginsDir "$DIR" plugins install <id> <version>`. Note
  `--pluginsDir` is a flag on `cli` itself (before the `plugins install` subcommand),
  not on `plugins install` — confirmed via `grafana cli --help`.
- **Related gotcha, same build step:** the image's `grafana` user has no matching
  `grafana` *group* — its actual group is `root` (gid 0). `chown -R grafana:grafana`
  fails with `unknown user/group`; use `chown -R grafana:root` (confirmed via `id`
  inside the container: `uid=472(grafana) gid=0(root)`).

### 12. jmx_exporter: the official Cassandra example's actual metric names differ from assumption

- **Symptom:** dashboard panels for disk usage and GC pauses show no data even though
  the exporter itself is scraping fine (Prometheus target `UP`, other Cassandra
  metrics present).
- **Cause, two separate issues:**
  1. The `Storage/Load` MBean (data-directory disk usage) exposes its value via a JMX
     `Count` attribute in this Cassandra version, not `Value` — jmx_exporter's generic
     rules therefore produce `cassandra_storage_load_count`, not the initially-assumed
     `cassandra_storage_load`.
  2. jmx_exporter's javaagent **auto-exports** `jvm_gc_collection_seconds_{count,sum}`
     from its own built-in JVM collector, completely independent of the
     `whitelistObjectNames`/`rules:` config. A custom rule added for
     `java.lang:type=GarbageCollector` (`jvm_gc_collection_count`/`_time_ms`) was
     silently never used — the built-in exporter's names won regardless.
- **How it was found:** curling the exporter's raw `/metrics` output directly and
  grepping for the expected names, rather than trusting the dashboard JSON was correct
  because the config "looked right."
- **Fix:** dashboard queries updated to `cassandra_storage_load_count` and
  `jvm_gc_collection_seconds_sum` (unit `s`, not `ms`); the redundant custom GC rule
  was deleted from `cassandra-jmx-exporter.yml` entirely rather than left as dead
  config.
- **General lesson:** don't trust an exporter config's *intended* metric names without
  checking the exporter's actual `/metrics` output — an MBean's attribute name
  (`Value` vs `Count`) isn't always what a generic rule pattern assumes, and some
  "custom" rules can be silently shadowed by an exporter's own built-in metric set.

### 13. CQL clause order: `LIMIT` before `ALLOW FILTERING`, not after

- **Symptom:** a Grafana panel query fails with
  `mismatched input 'LIMIT' expecting EOF` when the query ends in
  `... ALLOW FILTERING LIMIT 100`.
- **Cause:** CQL requires `LIMIT` to appear before `ALLOW FILTERING` in a `SELECT`
  statement — the reverse of what reads naturally in English ("filter everything,
  then limit the result").
- **How it was found:** testing the dashboard's exact query strings directly against
  Grafana's `/api/ds/query` HTTP endpoint with real parameter values substituted in,
  not just visually reviewing the JSON — this caught a syntax error that a JSON review
  alone would have missed entirely (the query is a plain string field from Grafana's
  point of view, never parsed until it reaches Cassandra).
- **Fix:** `... LIMIT 100 ALLOW FILTERING`.
- **General lesson:** for any datasource where the "query" is an opaque string inside
  dashboard JSON (raw SQL/CQL, PromQL, etc.), verify it by actually executing it
  through the real API before trusting the dashboard provisions cleanly — a valid JSON
  file can still contain a query that only fails once a user actually views the panel.

### 14. KPI-5 panels fail with a CQL parse error: bare `$granularity` isn't interpolated in a table-name position

- **Symptom:** all four KPI-5 ("Business aggregates") panels error with something like
  `p.ExecQuery: query processing: repo.Select: select query processing: line 1:61
  mismatched character 'g' expecting '$'` — a CQL parser complaint, not a Grafana-level
  error.
- **Cause:** the panel queries used bare `$granularity` in the `FROM` clause
  (`FROM iot.$granularity WHERE ...`), while the working `device_id` variable elsewhere
  in the same queries used the curly-brace form (`${device_id:singlequote}`). The bare
  form was never actually substituted before the query reached Cassandra — the literal
  string `"...iot.$granularity WHERE..."` was sent as-is. Cassandra's CQL grammar
  treats a bare `$` as the start of a dollar-quoted string literal (it expects a second
  `$` immediately after), so it fails parsing at the character right after the `$`,
  which is exactly what the error position points at.
- **How it was found:** reproduced the *exact* error message directly against the real
  Cassandra container via `cqlsh`, using the literal unsubstituted query text — then
  confirmed the same query works and returns real rows once `$granularity` is replaced
  with a real value (`agg_1m`). Same "test wall-first against the real Cassandra
  service, don't stop at the dashboard JSON" approach as bug #13. Confirmed the fix
  itself by editing the dashboard JSON, restarting Grafana, and loading the actual
  panel in a browser to see real data render, not just re-reading the query string.
- **Fix:** `FROM iot.${granularity} WHERE ...` in all four KPI-5 panel queries
  (`infra/grafana/provisioning/dashboards/json/kpi-dashboard.json`).
- **Related, NOT a bug — don't re-"fix" this:** once the query itself is correct, the
  KPI-5 panels can still legitimately show **"No data"** for a while after a fresh
  deploy. `window_start` is derived from each row's own `event_ts`
  (`spark_job/spark_job/time_buckets.py`), and during REPLAY mode `event_ts` is a
  historical Kaggle-dataset date (e.g. `2020-07-15`) — confirmed by querying `agg_1m`
  directly via `/api/ds/query` and seeing real `window_start` values from 2020. Since
  the panels filter `window_start > $__timeFrom AND window_start < $__timeTo`, which
  Grafana resolves to real wall-clock "now," **no row can ever match while REPLAY mode
  is still running**, no matter how long you wait or how wide the time range. This
  resolves itself automatically once the producer hands over to SYNTHETIC mode (real
  timestamps) — or force it sooner for testing with `PRODUCER_REPLAY_ROW_LIMIT` (see
  the root README). This is the same wall-clock-vs-event-time root cause as P5 bug #1
  above, just surfacing in a Grafana panel instead of the web app's backend — the web
  app's fix (deriving buckets from real observed timestamps) doesn't generalize to a
  Grafana time-range picker, since Grafana has no equivalent of "ask the live data what
  time it actually is."
- **General lesson:** don't assume Grafana's bare `$var` and `${var}` interpolation are
  interchangeable in every position a query might use them — when a query mixes both
  forms and only one position fails, that inconsistency itself is a signal; prefer
  `${var}` everywhere for raw-query datasources to remove the ambiguity entirely rather
  than debugging which bare form happens to work where.

### General P4 lesson

Every finding above was caught by one of two things: reading an official upstream
example/tool's output directly (the real jmx_exporter Cassandra example, the real
`grafana cli --help` output, the real `/metrics` text) instead of trusting a
plan/memory reconstruction of it, or actually executing the exact query/command a
dashboard or Dockerfile would run, rather than treating "the config looks right" as
sufficient. Both are cheap to do and catch an entire class of bug that a syntax-only
review cannot.

---

## P5 — Web app (FastAPI backend + React frontend)

### 1. "Recent Cassandra rows" query returns nothing (or stale data) during REPLAY mode

- **Symptom:** the Cassandra step's "recent rows" panel showed old/unrelated rows
  (or none) for most of a fresh walkthrough session, only becoming correct once the
  producer handed over to synthetic generation.
- **Cause:** `raw_events`' partition key is `(device_id, bucket_start)`, where
  `bucket_start` is derived from each row's own `event_ts`
  (`spark_job/spark_job/time_buckets.py`) — NOT from wall-clock time. During REPLAY
  mode, `event_ts` comes from the historical Kaggle dataset (e.g. `2020-07-12`), so a
  query that guesses "the current bucket" from `datetime.now()` queries buckets that
  replay-mode rows never land in.
- **How it was found:** noticed the Cassandra step showed a fixed set of rows with a
  `write_ts` far earlier than "just now" while watching the live UI, then cross-checked
  the actual event/bucket timestamps being produced via `/api/steps/ingestion` against
  what `/api/steps/cassandra` was querying for — not caught by a design review, only by
  watching real replay traffic.
- **Fix:** `backend/app/cassandra_client.py`'s `recent_raw_events_sync` now takes
  `reference_timestamps` (sampled from real Kafka messages via
  `kafka_client.KafkaReader.get_recent_events()`) and derives the buckets to query from
  those, falling back to wall-clock buckets only when no samples exist yet (cold start).
  Still single-partition point reads — no `ALLOW FILTERING` needed.

### 2. One transient upstream hiccup crashed the entire frontend (blank/frozen page)

- **Symptom:** restarting the `producer` container mid-session (used to test UC-3's
  hand-over) sometimes left the whole web app frozen on a `Loading...` screen
  requiring a manual reload. Console showed
  `TypeError: Cannot read properties of undefined (reading 'toLocaleString')`.
- **Cause:** `state_poller.py`'s `_refresh_fast` built the `ingestion` step by spreading
  `producer_state` (from polling `producer:8000/state`) directly into the response dict.
  When that poll failed (producer briefly unreachable during its own restart),
  `producer_state` was `None`, so the `ingestion` object silently lost fields like
  `events_sent_total` — and `IngestionStep.tsx` called `.toLocaleString()` on it
  unconditionally. React 18 unmounts the *entire* root on an uncaught render error with
  no `ErrorBoundary` in place, so one step's bad data took down the whole walkthrough,
  not just that step.
- **How it was found:** actually restarting `producer` mid-session in a live browser tab
  while watching the console (per the plan's own "verify against the real system"
  practice) — a static read of the code looked fine because nothing there assumes
  upstream fetches always succeed until you watch what happens when one doesn't.
- **Fix, two layers:** (1) `state_poller.py` now caches the last-known-good
  `producer_state`/`spark_state` and merges new data on top of that cache instead of on
  top of `{}`, so the response shape stays stable across a transient outage —
  `source_reachable` still reflects the *current* poll so the UI can say "showing last
  known data". (2) `IngestionStep.tsx` also got defensive fallbacks (`?? 0`, `?? "-"`,
  `?? []`) as a second line of defense, and every step is now wrapped in a small
  `ErrorBoundary` (`frontend/src/layout/ErrorBoundary.tsx`, keyed by the current step)
  so a *future* bug in one step's rendering can't freeze the whole app again.

### 3. `/api/anomalies` (and the Grafana anomaly-drill-down panel it mirrors) risks `READ_TOO_MANY_TOMBSTONES` as data volume grows — not fixed, flagged for later

- **Symptom:** while cross-checking an anomaly row directly via `cqlsh` using the same
  `device_id IN (...) ... ALLOW FILTERING` shape (without a `bucket_start`), one query
  failed outright with `ReadFailure: ... READ_TOO_MANY_TOMBSTONES`; the same shape *with*
  `bucket_start` narrowing to one partition succeeded but logged a tombstone warning
  (~6,800 tombstone cells read alongside ~7,150 live rows in a single 15-minute bucket).
- **Likely cause (not confirmed further):** the spark-cassandra-connector writes `NULL`
  Row fields as per-column tombstones by default; `raw_events` has several
  usually-null columns (`anomaly_reason` on the ~95% of rows that aren't anomalies), so
  tombstones accumulate quickly at hundreds of rows/sec with no TTL/compaction pressure
  to clear them.
- **Why not fixed now:** `/api/anomalies` reuses the exact CQL shape already
  provisioned (and accepted) for the P4 Grafana panel
  (`infra/grafana/provisioning/dashboards/json/kpi-dashboard.json`), scoped by
  `since_minutes`/`LIMIT` so it stayed well under the failure threshold in this
  session's testing — but the underlying risk is shared by both the Grafana panel and
  this new endpoint, and grows with data volume/retention, not with anything P5 added.
  A real fix (e.g. `unset` instead of `null` for optional columns in the Spark sink, or
  a lower `gc_grace_seconds`/more frequent compaction) is a P3/Cassandra-schema-level
  change, out of scope for this phase.

### General P5 lesson

Both real bugs (#1 and #2) were invisible from reading the code or the JSON contract
alone — they only showed up when actually watching live REPLAY-mode traffic and
actually killing a container mid-session in a real browser tab, matching this
project's established practice of verifying every phase against the running system
rather than trusting a design as correct because it reads correctly.

---

## P6 — VPS deployment (interim single-host Compose, see docs/DEPLOYMENT.md)

### 1. `producer` crash-loops on a fresh VPS deploy: `FileNotFoundError: /data/iot_telemetry_data.csv`

- **Symptom:** `producer` restarts forever with a Python traceback ending in
  `FileNotFoundError: [Errno 2] No such file or directory:
  '/data/iot_telemetry_data.csv'`, immediately after `producer_starting` logs.
- **Cause:** the Kaggle dataset isn't committed to the repo (~62 MB, gitignored) and
  the only way to get it in place was a manual host-side step
  (`python kaggle_repository/download_repository.py`) documented in the README — easy
  to skip entirely on a fresh VPS clone, especially since nothing about
  `docker compose up -d` itself hints that a non-Docker prerequisite exists.
  Compounding this: even once noticed, `pip install --user kagglehub` fails outright
  on modern Debian/Ubuntu with `error: externally-managed-environment` (PEP 668) — the
  system's own pip refuses a bare global install, and the "quick" fixes people reach
  for (`--break-system-packages`, or "just use `sudo`") both fight the OS's package
  management rather than working with it.
- **Fix:** removed the manual step entirely. A new one-shot `dataset-init` service
  (own directory `kaggle_repository/`, own `Dockerfile` + hash-pinned
  `requirements.txt`) downloads the dataset into a named volume (`kaggle_dataset`)
  automatically as part of `docker compose up -d` — the same idiom this project
  already uses for `kafka-topic-init`/`cassandra-schema-init`. `producer`, `spark-job`,
  and `spark-worker` now all mount that named volume read-only instead of a
  `./kaggle_repository` host bind-mount, and all three `depends_on:
  dataset-init: condition: service_completed_successfully`. Idempotent by design
  (`download_repository.py` checks whether the target file already exists before
  attempting a download), so it's a fast no-op on every restart after the first.
- **A pleasant surprise while fixing this:** the dataset turned out to need **no
  Kaggle credentials at all** for an anonymous download via `kagglehub` — confirmed by
  actually running the fetch with none configured, not assumed from the library's
  docs. `KAGGLE_USERNAME`/`KAGGLE_KEY` are kept as optional `.env` fallbacks (empty by
  default) for if that ever changes, rather than required vars — a required-but-usually-
  empty credential would have been worse UX than no requirement at all.
- **General lesson:** a "prerequisite" that lives outside `docker compose up -d` in a
  README step is a deployment footgun waiting to happen — if a real container can do
  the fetch/setup step itself (even a trivial one-shot one), that's more robust than
  documenting a manual step well, because it can't be skipped by accident.
