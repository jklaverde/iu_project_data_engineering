# Backend (P5 — web app API)

Read-only FastAPI backend behind a guided walkthrough UI (REQUIREMENTS.md
FR-W1-W5). Polls the already-running `producer`/`spark-job` `/state`
endpoints, Kafka, and Cassandra, and pushes a combined snapshot to the
browser over WebSocket (with an HTTP polling fallback). See the root
`README.md` for the full-stack quick start — normally this runs as the
`backend` service in `docker-compose.yml`, built together with `frontend/`
into one container (see `Dockerfile` — its build context is the repo root).

## Auth

A single admin credential (`BACKEND_ADMIN_USERNAME`/`BACKEND_ADMIN_PASSWORD`,
required env vars, no defaults) and a hand-rolled HMAC-SHA256-signed session
cookie (`app/auth.py`) — no session-management dependency, since there's a
single static credential rather than a user table. `require_session` guards
every `/api/steps/*` and `/api/anomalies` route, plus the `/ws/pipeline-state`
handshake (checked before `accept()`).

## Reserved for later

`/api/control/*` is not implemented — this is the seam UC-7's control panel
(pause/resume producer, trigger hand-over, etc.) will need in a later phase.
No `routers/control.py` exists yet; this note exists so that seam doesn't
need to be rediscovered.

## Hash-pinned dependencies (NFR-10.8)

`requirements.in` lists direct dependencies; `requirements.txt` is generated
via `pip-compile --generate-hashes` run inside a container matching this
service's own runtime base image (`python:3.11.9-slim-bookworm`) — not on a
dev machine directly, since hash-locked wheels are platform-specific. To
regenerate after changing `requirements.in`:

```
docker run --rm -v "$(pwd):/work" -w /work python:3.11.9-slim-bookworm \
  sh -c "pip install pip-tools && pip-compile --allow-unsafe --generate-hashes --output-file=requirements.txt requirements.in"
```

`producer/` and `spark_job/` follow the same pattern (each against their own
base image) — see their `requirements.in` files.
