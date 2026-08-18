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
