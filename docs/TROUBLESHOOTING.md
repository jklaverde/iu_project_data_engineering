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
