#!/usr/bin/env bash
# D43: brings the whole stack up on a local k3d (k3s-in-Docker) cluster,
# replacing `docker compose up -d --build --wait` as the local dev
# entrypoint. docker-compose.yml is kept as a historical/legacy reference
# (REQUIREMENTS.md D43) and still works on its own for anyone who wants it,
# but this is now the primary path.
#
# NOTE (fork-authored, not live-verified): this script was written without
# access to a live Docker/k3d/kubectl environment in the implementing
# sandbox - the k3d cluster-create flags and `kubectl wait` sequencing below
# are best-effort, based on k3d/kubectl's documented syntax, not a
# successful end-to-end run. See docs/operations.html's D43 section for
# what to check first if this doesn't work cleanly.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLUSTER_NAME="iot-pipeline"
NAMESPACE="iot-pipeline"

cd "$ROOT_DIR"

for bin in k3d kubectl docker; do
  command -v "$bin" >/dev/null 2>&1 || { echo "error: $bin not found on PATH" >&2; exit 1; }
done

if [ ! -f .env ]; then
  echo "error: .env not found - copy .env.example to .env and set the REQUIRED values first" >&2
  exit 1
fi

# 1. Cluster (idempotent - reuses an existing cluster of the same name).
if ! k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "==> Creating k3d cluster '$CLUSTER_NAME'"
  # Maps host 8000/3000 through k3d's built-in serverlb to the cluster's
  # `backend`/`grafana` Services, which are type: LoadBalancer (see
  # k8s/base/deployment-backend.yaml, deployment-grafana.yaml) so k3d's
  # klipper servicelb binds these host ports to them - this is k3d's
  # documented pattern for exposing a Service without an Ingress controller.
  k3d cluster create "$CLUSTER_NAME" \
    -p "8000:8000@loadbalancer" \
    -p "3000:3000@loadbalancer"
else
  echo "==> Reusing existing k3d cluster '$CLUSTER_NAME'"
fi

# 2. Build every locally-built image and import it into the cluster (k3d
# nodes don't share the host's Docker image store, so a plain `docker build`
# alone isn't visible to the cluster - `k3d image import` copies it in).
echo "==> Building local images"
docker build -t iu-sensor-pipeline/backend:local -f backend/Dockerfile .
docker build -t iu-sensor-pipeline/producer:local -f producer/Dockerfile producer
docker build -t iu-sensor-pipeline/cassandra:local -f infra/cassandra/Dockerfile infra/cassandra
docker build -t iu-sensor-pipeline/spark-job:local -f spark_job/Dockerfile spark_job
docker build -t iu-sensor-pipeline/spark-worker:local -f spark_job/worker.Dockerfile spark_job
docker build -t iu-sensor-pipeline/grafana:local \
  --build-arg "CASSANDRA_PLUGIN_VERSION=${GRAFANA_CASSANDRA_PLUGIN_VERSION:-3.3.0}" \
  -f infra/grafana/Dockerfile infra/grafana
docker build -t iu-sensor-pipeline/dataset-init:local -f kaggle_repository/Dockerfile kaggle_repository

echo "==> Importing images into k3d cluster '$CLUSTER_NAME'"
k3d image import \
  iu-sensor-pipeline/backend:local \
  iu-sensor-pipeline/producer:local \
  iu-sensor-pipeline/cassandra:local \
  iu-sensor-pipeline/spark-job:local \
  iu-sensor-pipeline/spark-worker:local \
  iu-sensor-pipeline/grafana:local \
  iu-sensor-pipeline/dataset-init:local \
  -c "$CLUSTER_NAME"

# 3. Stage k8s/base/kustomization.yaml's configMapGenerator sources.
# kustomize refuses to reference a file outside the kustomization root
# (k8s/base) as a security restriction, so the actual source of truth
# (infra/) gets mirrored into a gitignored k8s/base/generated/ before every
# apply, instead of duplicating these files into k8s/base for real.
echo "==> Staging config sources into k8s/base/generated"
GEN="$ROOT_DIR/k8s/base/generated"
rm -rf "$GEN"
mkdir -p "$GEN/cassandra-schema" "$GEN/grafana"
cp infra/cassandra/schema/*.cql "$GEN/cassandra-schema/"
cp infra/prometheus/prometheus.yml "$GEN/prometheus.yml"
cp infra/loki/loki-config.yml "$GEN/loki-config.yml"
cp infra/promtail/promtail-config-k8s.yml "$GEN/promtail-config-k8s.yml"
cp infra/grafana/provisioning/datasources/datasources.yaml "$GEN/grafana/"
cp infra/grafana/provisioning/dashboards/dashboards.yaml "$GEN/grafana/"
cp infra/grafana/provisioning/dashboards/json/kpi-dashboard.json "$GEN/grafana/"
cp infra/grafana/provisioning/alerting/contactpoints.yaml "$GEN/grafana/"
cp infra/grafana/provisioning/alerting/policies.yaml "$GEN/grafana/"
cp infra/grafana/provisioning/alerting/rules.yaml "$GEN/grafana/"

# 4. Namespace first, so the Secret below has somewhere to go.
kubectl apply -f "$ROOT_DIR/k8s/base/namespace.yaml"

# 5. Secret, generated from .env - never committed, same rule as
# docker-compose.yml's own .env usage (D43, REQUIREMENTS.md §4.4).
# NOT `source .env`: several of this project's existing .env values contain
# unquoted spaces (e.g. SPARK_JOB_TRIGGER_INTERVAL=30 seconds), which is
# valid Compose env-file syntax but breaks shell `source` (bash tries to run
# `seconds` as a command). Extract only the handful of keys actually needed
# here, per-line, without shell-interpreting the rest of the file.
echo "==> Generating app-secrets Secret from .env"
env_value() {
  grep -m1 "^${1}=" .env | cut -d'=' -f2-
}
GRAFANA_ADMIN_PASSWORD="$(env_value GRAFANA_ADMIN_PASSWORD)"
BACKEND_ADMIN_PASSWORD="$(env_value BACKEND_ADMIN_PASSWORD)"
BACKEND_PLANNER_PASSWORD="$(env_value BACKEND_PLANNER_PASSWORD)"
BACKEND_SESSION_SECRET="$(env_value BACKEND_SESSION_SECRET)"
KAGGLE_USERNAME="$(env_value KAGGLE_USERNAME)"
KAGGLE_KEY="$(env_value KAGGLE_KEY)"
kubectl create secret generic app-secrets \
  --namespace "$NAMESPACE" \
  --from-literal="GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD in .env}" \
  --from-literal="BACKEND_ADMIN_PASSWORD=${BACKEND_ADMIN_PASSWORD:?Set BACKEND_ADMIN_PASSWORD in .env}" \
  --from-literal="BACKEND_PLANNER_PASSWORD=${BACKEND_PLANNER_PASSWORD:?Set BACKEND_PLANNER_PASSWORD in .env}" \
  --from-literal="BACKEND_SESSION_SECRET=${BACKEND_SESSION_SECRET:?Set BACKEND_SESSION_SECRET in .env}" \
  --from-literal="KAGGLE_USERNAME=${KAGGLE_USERNAME:-}" \
  --from-literal="KAGGLE_KEY=${KAGGLE_KEY:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

# 6. Everything else.
echo "==> Applying k8s/base (kustomize)"
kubectl apply -k "$ROOT_DIR/k8s/base"

# 7. Best-effort readiness wait - see the header note above. Individual
# pods that start before a dependency is ready recover on their own via
# their initContainer TCP-wait loops and normal pod restart backoff, so
# this is user feedback, not a strict release gate.
echo "==> Waiting for cassandra and kafka to become ready (this can take a few minutes)"
kubectl -n "$NAMESPACE" rollout status statefulset/cassandra --timeout=300s || true
kubectl -n "$NAMESPACE" rollout status statefulset/kafka --timeout=180s || true

echo "==> Waiting for one-shot init Jobs"
kubectl -n "$NAMESPACE" wait --for=condition=complete --timeout=300s \
  job/kafka-topic-init job/cassandra-schema-init job/dataset-init || true

echo "==> Waiting for backend and grafana"
kubectl -n "$NAMESPACE" rollout status deployment/backend --timeout=300s || true
kubectl -n "$NAMESPACE" rollout status deployment/grafana --timeout=180s || true

cat <<EOF

==> Up. Backend:  http://localhost:8000
==> Grafana:      http://localhost:3000
==> Everything else (spark UIs, kafka-ui, prometheus, kafka-exporter, ...)
    is cluster-internal only in this pass (D43 narrows host exposure to
    just backend/grafana) - use 'kubectl -n $NAMESPACE port-forward' to
    reach them if you need to during development.
EOF
