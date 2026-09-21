# iu_project_data_engineering
Project: Data Engineering for IU Akademie

A role-based environmental sensor platform for the municipality of Lingen (Ems) — Kafka →
Spark Structured Streaming → Cassandra underneath, with two web app roles on top: an
**environmental/planner** role (a live sensor map, air quality scoring, behavior-over-time
charts, and an out-of-range log) and an **infrastructure/admin** role (the pipeline health
tour, centralized logs, Grafana-fired alerts with log drill-down) — plus a Grafana KPI
dashboard, all deployed with one script, `./k8s/deploy.sh <local|prod> up` — a local
Kubernetes/k3d cluster for development, or a native k3s host for production, from the
same manifests. (`docker compose up -d` remains as a legacy fallback.) See
`REQUIREMENTS.md` for the full project scope and phase roadmap, and **`docs/index.html`**
for everything else — open it directly in a browser (no server needed) for the full
documentation site: how the system is built (every module explained, animated
data-flow/boot-order diagrams, a per-container reference), how to deploy it on a public
VPS with k3s, current status and non-obvious bugs/gotchas found while building and operating the
stack, and a file-by-file reference for the whole repo.

## Prerequisites

- **Docker Engine** (Docker Desktop with the WSL2 backend on Windows) — builds the custom
  images in *every* environment.
- **`kubectl`** (on a k3s host, the `k3s` binary bundles it as `k3s kubectl`).
- **Local dev:** [k3d](https://k3d.io/) (k3s-in-Docker). Nothing else — it creates the
  cluster for you.
- **Production:** a host that already has **k3s installed and hardened** — SSH, firewall,
  k3s itself: [`docs/deployment.html`](docs/deployment.html) §1–3. `deploy.sh` deliberately
  never installs k3s or hardens the machine (see [why](#local-vs-production-what-differs-and-why)).
- ~16 GB RAM / 4 CPU cores free, ~25 GB free disk for normal use (see `REQUIREMENTS.md`
  NFR-3 for the 48-hour endurance-run sizing). The 11 GB VPS this project was verified on
  runs out of memory headroom when everything runs at once (`REQUIREMENTS.md` D44/D45).
- Internet access on first start, so the `dataset-init` job can fetch the Kaggle source
  dataset — see [Dataset](#dataset). No manual download step.

## Bringing the infrastructure up and down

**One script deploys every environment: `k8s/deploy.sh <local|prod> <command>`.** Both
environments apply the *same* Kubernetes manifests (`k8s/base`) through the *same* steps;
the small number of places where they genuinely have to differ are listed, with the
reason for each, in [Local vs production](#local-vs-production-what-differs-and-why).

| Command | What it does |
|---|---|
| `check` | Validates tools, `.env`, the cluster and (prod) the host. **Changes nothing** — run it first. |
| `up` | Brings the whole stack up. Idempotent: safe to re-run. |
| `update <service>...` | Rebuilds the named image(s) and rolling-restarts them — **how a code change goes live**. |
| `status` | Pods, PVCs and Services in the `iot-pipeline` namespace. |
| `down [--yes]` | Tears down. Local: the whole disposable cluster. Prod: only the namespace and its data. |

Services accepted by `update`: `backend producer cassandra spark-job spark-worker grafana
dataset-init`. `k8s/local-up.sh` and `k8s/local-down.sh` still exist as one-line wrappers
for `deploy.sh local up` / `deploy.sh local down`.

### Local dev, on your own machine

```
cp .env.example .env
# edit .env: set real values for GRAFANA_ADMIN_PASSWORD, BACKEND_ADMIN_PASSWORD,
# BACKEND_PLANNER_PASSWORD and BACKEND_SESSION_SECRET (e.g. `openssl rand -hex 32`)

./k8s/deploy.sh local check
./k8s/deploy.sh local up
```

First start creates a k3d cluster, builds the seven custom images, loads them into it,
generates the `app-secrets` Secret from `.env`, and applies `k8s/base`. It takes several
minutes on a cold start (pre-warming Spark's dependency cache, fetching the Kaggle
dataset). When done it prints **http://localhost:8000** (backend) and
**http://localhost:3000** (Grafana) and a pod summary. Nothing else is exposed to the host
(`REQUIREMENTS.md` §4.4); use `kubectl -n iot-pipeline port-forward` for Spark UIs,
Prometheus, etc. (`kafka-ui` is scaled to 0 by default to save memory — `kubectl -n
iot-pipeline scale deployment kafka-ui --replicas=1` first).

Tear down (deletes the whole cluster and every PVC's data — a clean slate):
```
./k8s/deploy.sh local down
```

### Production (a host running k3s)

Prerequisite: the host is provisioned, hardened and has k3s installed —
[`docs/deployment.html`](docs/deployment.html) §1–3. Then, **on that host**, from a clone
of this repo:

```
cp .env.example .env
# edit .env: real values for the four secrets above. Placeholders ("changeme...") and a
# session secret shorter than 32 characters are REJECTED in prod.
# Non-secret settings are NOT here - see "Where configuration lives" below.

sudo ./k8s/deploy.sh prod check     # read-only: k3s active? API reachable? storage class? .env sane?
sudo ./k8s/deploy.sh prod up
```

(`sudo`/root is needed because k3s writes its kubeconfig root-only and `k3s ctr` talks to
a root-owned containerd socket. To run as a normal user instead, copy the kubeconfig
somewhere readable and set `PROD_KUBECONFIG=<path>`; you'd still need `sudo` for image
loading.)

`up` prints the URLs (`http://<host-ip>:8000`, `:3000`), a pod summary, and warns if
anything isn't `Running`/`Completed` yet. **Production is plain HTTP until TLS is set up** —
`docs/deployment.html` §6 covers the interim reverse proxy; native ingress/TLS is part of
"full P6" (`REQUIREMENTS.md` §4.1) and is not built yet.

Tear down (irreversible; asks you to type the namespace name to confirm):
```
sudo ./k8s/deploy.sh prod down
```
This removes only the `iot-pipeline` namespace and its PVC data. k3s itself, its system
pods and the rest of the host are left alone.

### Where configuration lives

This is the single most common source of confusion, because two files look alike.

| What | File | Read by | To change it |
|---|---|---|---|
| **Secrets** — the 4 passwords/secrets + optional Kaggle credentials | `.env` (never committed) | `deploy.sh` → Kubernetes Secret `app-secrets` | edit `.env`, run `deploy.sh <env> up` |
| **Non-secret settings** — producer rate, replay row limit, watermarks, `BACKEND_COOKIE_SECURE`, Cassandra storage budget, … | `k8s/base/config.env` (committed) | ConfigMap `app-config` | edit it, run `deploy.sh <env> up` — the ConfigMap is content-hashed (`kustomization.yaml`), so the pods that reference it roll automatically |
| Everything else in `.env` (host ports, `*_PORT`, …) | `.env` | **`docker compose` only** | — |

So on Kubernetes (local *and* prod), **`.env` is only read for the secrets**. Setting
`PRODUCER_RATE_MSGS_PER_SEC=500` in `.env` does nothing there — that key lives in
`k8s/base/config.env`. `deploy.sh` warns when a key exists in both files with different
values, so this can't silently bite you.

### Local vs production: what differs, and why

The manifests, the Secret flow, the config files, the config staging, the readiness
checks and the image tags are **identical**. What differs is only what has to:

| Aspect | Local (`deploy.sh local`) | Production (`deploy.sh prod`) | Why it differs |
|---|---|---|---|
| **Who owns the cluster** | Creates it on `up`, deletes it on `down` | Never creates or deletes k3s; manages only the `iot-pipeline` namespace | A dev cluster is disposable — a clean slate is the point. The prod cluster is long-lived host infrastructure (installed once by the operator, possibly running other workloads); a project script must not be able to remove it. |
| **Kubernetes flavor** | **k3d** — k3s inside Docker containers | **k3s** — native, as a systemd service on the host | Same k3s distribution in both (`REQUIREMENTS.md` D43), so the manifests behave the same. k3d gives a throwaway cluster on any laptop with just Docker; on a server, running k3s directly avoids a Docker-in-Docker layer and gives the cluster its own lifecycle (D18). |
| **How images get in** | `k3d image import` | `docker save … \| k3s ctr images import -` | The two clusters keep images in different stores. k3d's nodes are containers with their own store; native k3s runs its **own** containerd, separate from Docker's (`docker ps` is empty while k3s pods run). There is no registry yet, so images are loaded directly. |
| **Which kubeconfig** | `k3d kubeconfig write` | `/etc/rancher/k3s/k3s.yaml` (override: `PROD_KUBECONFIG`) | Both are *explicit*, never the ambient one. On a k3s host `kubectl` silently defaults to the k3s kubeconfig and ignores `~/.kube/config` — the D46 bug, which would send a "local" deploy to production (or the reverse). |
| **How ports reach the host** | `-p 8000:8000@loadbalancer` mapping at cluster creation | k3s' built-in servicelb binds host ports 8000/3000; the host firewall (`ufw`) decides who can reach them | The `backend`/`grafana` Services are `type: LoadBalancer` in both — one manifest. k3d's "node" is a container, so its ports must be mapped when the cluster is created; native k3s binds directly on the host. |
| **Config validation** | Placeholder secrets allowed (e.g. `changeme`) | Placeholders and a <32-char session secret are fatal errors | Local is reachable only from the developer's machine. Prod is internet-facing: a default credential there is a vulnerability, not a convenience. |
| **`down`** | No confirmation; deletes the cluster | Lists the PVCs to be destroyed and requires typing the namespace name (or `--yes`); refuses without a terminal | Local data is disposable. Prod's Cassandra volumes are the **only copy** of the sensor history and deletion is irreversible. |
| **Node count** | 1 | 1 today; **multi-node is refused** by the script | Images are loaded into one host's containerd only, and every PVC uses `local-path` (one node's disk). On a 3-node cluster pods would land on nodes without the images or the volumes. The fix — a registry, RWX storage, ingress/TLS, WireGuard — is the unbuilt production Kustomize overlay ("full P6"). |
| **What is *not* in `deploy.sh`** | — | Host hardening, k3s installation, TLS, backups, reboot survival | These are one-time or ongoing *operator* tasks on a specific machine, not part of a repeatable app deploy. They are documented step by step in [`docs/deployment.html`](docs/deployment.html). |

**Known gaps in production, stated plainly** (`REQUIREMENTS.md` D48 and §4.1): no TLS/ingress
(traffic is plain HTTP), single node, no registry, no automated backups. None of these are
"how prod differs on purpose" — they are unbuilt work, and `deploy.sh` is written so an
overlay can add them without changing how you run it.

### What `deploy.sh up` does, step by step

If you want to run it by hand (or understand what's happening), these are the steps, from the
repo root. `<…>` marks the part that differs by environment.

```
# 0. Config sanity - what `check` does. Never `source .env`: some values contain spaces.

# 1. Cluster
local:  k3d cluster create iot-pipeline -p "8000:8000@loadbalancer" -p "3000:3000@loadbalancer"
        export KUBECONFIG="$(k3d kubeconfig write iot-pipeline)"
prod:   export KUBECONFIG=/etc/rancher/k3s/k3s.yaml            # k3s already exists

# 2. Build the seven custom images (same in both)
docker build -t iu-sensor-pipeline/backend:local      -f backend/Dockerfile .
docker build -t iu-sensor-pipeline/producer:local     -f producer/Dockerfile producer
docker build -t iu-sensor-pipeline/cassandra:local    -f infra/cassandra/Dockerfile infra/cassandra
docker build -t iu-sensor-pipeline/spark-job:local    -f spark_job/Dockerfile spark_job
docker build -t iu-sensor-pipeline/spark-worker:local -f spark_job/worker.Dockerfile spark_job
docker build -t iu-sensor-pipeline/grafana:local --build-arg CASSANDRA_PLUGIN_VERSION=3.3.0 \
             -f infra/grafana/Dockerfile infra/grafana
docker build -t iu-sensor-pipeline/dataset-init:local -f kaggle_repository/Dockerfile kaggle_repository

# 3. Load them into the cluster
local:  k3d image import iu-sensor-pipeline/{backend,producer,cassandra,spark-job,spark-worker,grafana,dataset-init}:local -c iot-pipeline
prod:   for i in backend producer cassandra spark-job spark-worker grafana dataset-init; do
          docker save iu-sensor-pipeline/$i:local | k3s ctr images import -
        done

# 4. Stage config sources (kustomize can't read outside k8s/base; k8s/base/generated is gitignored)
#    copy: infra/cassandra/schema/*.cql, infra/prometheus/prometheus.yml, infra/loki/loki-config.yml,
#    infra/promtail/promtail-config-k8s.yml and the Grafana provisioning files - see deploy.sh's
#    stage_generated() for the exact list. Skipping this makes step 6 fail on a fresh clone.

# 5. Namespace FIRST (the Secret needs somewhere to go), then the Secret from .env
kubectl apply -f k8s/base/namespace.yaml
kubectl create secret generic app-secrets -n iot-pipeline \
  --from-literal=GRAFANA_ADMIN_PASSWORD=... --from-literal=BACKEND_ADMIN_PASSWORD=... \
  --from-literal=BACKEND_PLANNER_PASSWORD=... --from-literal=BACKEND_SESSION_SECRET=... \
  --from-literal=KAGGLE_USERNAME= --from-literal=KAGGLE_KEY=
#    (deploy.sh pipes `--dry-run=client -o yaml` into `kubectl apply -f -` so re-running updates
#     the Secret instead of failing "already exists", and strips trailing "# comments" from values.)

# 6. Everything else
kubectl apply -k k8s/base

# 7. Watch it come up (cassandra, kafka, the 3 init Jobs, backend, grafana)
kubectl -n iot-pipeline get pods -w
```

### Changing things on a running stack

Three different kinds of change, three different commands — mixing them up is the usual
reason "I changed it and nothing happened":

| You changed… | Run | Why |
|---|---|---|
| **Application code** (`backend/`, `producer/`, `spark_job/`, `infra/cassandra/`, `infra/grafana/`) | `deploy.sh <env> update <service>` | Images are tagged `:local`. Re-importing an image under the same tag isn't a change Kubernetes can see in the pod spec, so `up` alone leaves the **old** container running. `update` rebuilds, reloads and does a rolling restart. |
| **Settings** (`k8s/base/config.env`) or **secrets** (`.env`) | `deploy.sh <env> up` | The ConfigMap is content-hashed, so pods referencing it roll on their own. A changed *Secret* does not roll pods by itself: follow with `kubectl -n iot-pipeline rollout restart deployment/<name>` for the ones that read it. |
| **Manifests or `infra/` config** (`k8s/base/*.yaml`, Prometheus/Loki/Grafana provisioning) | `deploy.sh <env> up` | Re-stages `generated/` and re-applies. If `apply` complains that a Job field is *immutable*, delete that Job (`kubectl -n iot-pipeline delete job <name>`) and re-run `up` — the init Jobs are idempotent. |

Never repeat the full down/up cycle for a code change: it wipes Kafka/Cassandra/Grafana/
Prometheus state that has nothing to do with the change.

### Legacy: docker compose

`docker-compose.yml` is kept as a historical reference (`REQUIREMENTS.md` D43). It still runs
the full stack on a single host but is **no longer the production path**, and it differs from
the Kubernetes paths in ways that matter:

- The admin's Cassandra node-deploy and Kubernetes-status tabs return `503` (they need the
  Kubernetes API).
- It publishes **every** service port on all interfaces (Kafka 9092, Cassandra 9042,
  Prometheus 9090, Spark UIs, …). Docker programs its own iptables rules, which **bypass
  `ufw`**, so a default-deny firewall does *not* protect them. Do not run it on a public host
  without binding those ports to `127.0.0.1` first (see `docs/deployment.html`, Appendix).
- It reads *all* its settings from `.env`, unlike the Kubernetes paths.

```
docker compose up -d --build --wait      # up
docker compose down                      # down, keeping named volumes
docker compose down -v                   # down, deleting all data (irreversible)
```
`--wait` blocks until every service with a healthcheck reports `healthy`; the `*-init` /
`*-schema-init` one-shot containers should show `Exited (0)`. If you rebuild one service by
name, run a bare `docker compose up -d --wait` afterwards to sweep anything that drifted to
`Exited` back up (`docs/operations.html#p9`).

### Differences at a glance

| | Local (`deploy.sh local`) | Production (`deploy.sh prod`) | Legacy (`docker compose`) |
|---|---|---|---|
| Up | `deploy.sh local up` | `deploy.sh prod up` | `docker compose up -d --build --wait` |
| Down | `deploy.sh local down` | `deploy.sh prod down` | `docker compose down -v` |
| Runtime | k3d (k3s in Docker) | native k3s | Docker only |
| What `down` destroys | The whole disposable cluster | The namespace and its data — k3s stays | All named volumes |
| Code change goes live via | `update <service>` | `update <service>` | `up -d --build` |
| Settings live in | `k8s/base/config.env` | `k8s/base/config.env` | `.env` |
| Admin Cassandra-deploy / K8s tabs | Work | Work | `503` |
| Host ports exposed | 8000, 3000 | 8000, 3000 (firewall-controlled) | **All of them** (bypasses ufw) |
| TLS | none (localhost) | none yet — plain HTTP | none |
| Best for | Trying it out, development | Real deployment | Historical fallback only |

## Walkthrough guide

Once the stack is healthy, open **http://localhost:8000** (local) or **http://\<host-ip\>:8000**
(production) and log in with one of the two
role accounts (usernames from `k8s/base/config.env`, passwords from `.env`) — the same login form serves both roles, which one you land on
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
`docker compose` path instead, since there's no cluster to ask. Works identically in local
and production, since both are Kubernetes.

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
in **`k8s/base/config.env`** (not `.env` — see [Where configuration
lives](#where-configuration-lives)) and run `./k8s/deploy.sh <env> up` — this replays only
the last N rows instead of the whole file.

Grafana (**http://localhost:3000** locally, `:3000` on the host in production; user from
`k8s/base/config.env`, password from `.env`) has the full KPI
dashboard (`REQUIREMENTS.md` §9: throughput/lag, latency, business aggregates, disk
growth, anomaly drill-down, and now logs) auto-provisioned — no manual setup needed.

## Continuing development

Picking this project up (as a person or a new Claude Code session)? Start with
[`CLAUDE.md`](CLAUDE.md): the catch-up checklist, the current state, the conventions that
keep the decision log honest, playbooks for a new requirement / milestone / incident, and the
gotchas that have already cost time. The prioritized backlog is `docs/operations.html` →
"Where to pick this up next"; the decision log is `REQUIREMENTS.md` §11.

## Endurance-run procedure

`REQUIREMENTS.md` §10 defines the acceptance run: 500 msg/s sustained for 48 hours with
no service failure. To run it:

1. Ensure the host meets the endurance sizing in `REQUIREMENTS.md` NFR-3
   (100 GB free disk minimum — retention has no TTL, so usage grows for the whole run).
2. Set `PRODUCER_RATE_MSGS_PER_SEC=500` in **`k8s/base/config.env`** (not `.env`, which
   the Kubernetes paths don't read for this) before starting.
3. Start the stack fresh so the 48-hour window starts from a clean baseline — see
   [Bringing the infrastructure up and down](#bringing-the-infrastructure-up-and-down):
   `./k8s/deploy.sh <local|prod> down && ./k8s/deploy.sh <local|prod> up` (production's
   `down` asks you to confirm), or `docker compose down -v && docker compose up -d --build`
   (legacy).
4. Watch Grafana throughout — KPI-1 (lag), KPI-2 (latency), and KPI-4 (disk growth) are
   the ones most likely to reveal a problem before it becomes a failure.
5. At the 48-hour mark, check the acceptance criteria in `REQUIREMENTS.md` §10 (no
   restarts, no sustained lag growth, disk within the sized budget, latency within
   NFR-1/NFR-2's bounds).

## Dataset

The Kaggle source dataset (§5.1 of `REQUIREMENTS.md`, `garystafford/environmental-sensor-data-132k`)
is not committed to the repo — it's ~62 MB and public. Both `./k8s/deploy.sh <env> up` and
`docker compose up -d` fetch it automatically via the one-shot `dataset-init`
service/Job (same pattern as `kafka-topic-init`/`cassandra-schema-init`): it downloads
into a `kaggle_dataset` volume/PVC that `producer`, `spark-job`, and `spark-worker` all
mount read-only, and skips the download entirely on future restarts once the volume
already has the file.

The dataset is public, so this needs **no credentials** in the common case. If Kaggle
ever requires auth for it, set `KAGGLE_USERNAME`/`KAGGLE_KEY` in `.env` (these are two of
the secrets `deploy.sh` copies into `app-secrets`) (from
https://www.kaggle.com/settings → API → Create New Token) — never commit those values.

To run the fetch by hand outside Docker (e.g. to inspect the CSV locally), see
`kaggle_repository/download_repository.py` — it takes the same env vars and writes to
`./kaggle_repository` by default.

## Deploying for real users

Production is `./k8s/deploy.sh prod up` on a host running k3s — the same script and the same
manifests as local development, with the differences listed and justified in [Local vs
production](#local-vs-production-what-differs-and-why). Everything *around* the script — sizing
the VPS, hardening SSH and the firewall, installing k3s, TLS, backups, surviving a reboot,
updating, monitoring, tearing down — is a step-by-step runbook in
[`docs/deployment.html`](docs/deployment.html). Two things to know before you expose it:

- **Traffic is plain HTTP** until TLS is added (`docs/deployment.html` §6). Native ingress/TLS
  is part of "full P6" (`REQUIREMENTS.md` §4.1) and is not built yet.
- It is a **single-node** deployment. The 3-VPS, HA-etcd target of §4.1 is still unbuilt;
  `deploy.sh` refuses to run against a multi-node cluster rather than half-deploying to one.

See `docs/operations.html`'s "Where to pick this up next" for exactly what is still missing.
