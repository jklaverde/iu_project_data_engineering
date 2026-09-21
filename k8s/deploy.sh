#!/usr/bin/env bash
# D48: the single entrypoint for deploying this stack, in every environment.
#
#   k8s/deploy.sh <local|prod> <command> [args]
#
# Both environments apply the SAME manifests (k8s/base) through the SAME steps
# (build images -> load them into the cluster -> stage generated config ->
# namespace -> Secret from .env -> kubectl apply -k -> wait). The only code
# that differs between `local` and `prod` is what genuinely has to differ, and
# every such branch below carries a comment saying why:
#
#   * who owns the cluster           (local creates/destroys it; prod never does)
#   * how images reach the cluster   (k3d image store vs. k3s' own containerd)
#   * which kubeconfig is used       (explicit in both, never ambient - D46)
#   * how destructive `down` may be  (prod asks for confirmation)
#   * how strict config validation is (prod refuses placeholder secrets)
#
# The full explanation and justification lives in README.md
# ("Local vs production: what differs, and why") and docs/deployment.html.
#
# Commands:
#   check             Validate prerequisites and config. Changes nothing.
#   up                Bring the stack up (idempotent - safe to re-run).
#   update <svc>...   Rebuild + reload the named image(s) and rolling-restart
#                     their workload. This is how a CODE change goes live;
#                     `up` alone does not (see cmd_update).
#   status            Show pods, PVCs and Services.
#   down [--yes]      Tear down. local: the whole k3d cluster. prod: only the
#                     iot-pipeline namespace and its data - never k3s itself.
#
# Environment variables (all optional):
#   PROD_KUBECONFIG=<path>    prod kubeconfig (default /etc/rancher/k3s/k3s.yaml)
#   LOCAL_CLUSTER_NAME=<name> k3d cluster name (default iot-pipeline)
#   SKIP_IMAGE_LOAD=1         `up` skips build+load (images delivered another way)
#
# (There is deliberately no shell-trace mode: `set -x` would print the secret
# values this script reads from .env.)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="iot-pipeline"
LOCAL_CLUSTER_NAME="${LOCAL_CLUSTER_NAME:-iot-pipeline}"
PROD_KUBECONFIG="${PROD_KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

# The custom images (everything not pulled from a public registry), in the
# order local-up.sh has always built them. Tag `:local` is what k8s/base
# references - see the Kubernetes rollout caveat in cmd_update.
SERVICES="backend producer cassandra spark-job spark-worker grafana dataset-init"

# prod only: `k3s ctr` talks to a root-owned containerd socket.
SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

say()  { echo "==> $*"; }
warn() { echo "warning: $*" >&2; }
die()  { echo "error: $*" >&2; exit 1; }

usage() {
  sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed -e '/^set -euo/d' -e 's/^# \{0,1\}//' >&2
  exit "${1:-2}"
}

# `kubectl` on a host with native k3s is often a symlink to the k3s binary
# (D46); on a host that only has the k3s binary, fall back to its subcommand.
kctl() {
  if command -v kubectl >/dev/null 2>&1; then kubectl "$@"; else k3s kubectl "$@"; fi
}

# file_value <file> <KEY>: the value of KEY in a KEY=VALUE env file, without
# shell-interpreting it. NOT `source`: several values contain unquoted spaces
# (e.g. SPARK_JOB_TRIGGER_INTERVAL=30 seconds), valid for Compose but not for
# bash. A trailing inline `# comment` (only when preceded by whitespace, so a
# bare `#` inside a value is kept) is stripped - otherwise .env's own
# "REQUIRED - ..." comments would be baked into the Secret's values.
file_value() {
  { grep -m1 "^${2}=" "$1" || true; } | cut -d'=' -f2- | tr -d '\r' | sed -E 's/[[:space:]]+#.*$//'
}

# ---------------------------------------------------------------- parsing ---
case "${1:-}" in -h|--help|help) usage 0 ;; esac
[ $# -ge 2 ] || usage
ENV_NAME="$1"; COMMAND="$2"; shift 2
case "$ENV_NAME" in local|prod) ;; *) echo "error: environment must be 'local' or 'prod', got '$ENV_NAME'" >&2; usage ;; esac

cd "$ROOT_DIR"

# ----------------------------------------------------------- prerequisites ---
# What each environment needs on PATH differs because the machinery differs.
check_tools() {
  local missing=0 bin
  local bins
  case "$ENV_NAME" in
    local) bins="k3d docker" ;;   # k3d creates the disposable cluster inside Docker
    prod)  bins="docker k3s" ;;   # docker builds images; `k3s ctr` loads them into containerd
  esac
  for bin in $bins; do
    command -v "$bin" >/dev/null 2>&1 || { echo "error: '$bin' not found on PATH" >&2; missing=1; }
  done
  command -v kubectl >/dev/null 2>&1 || command -v k3s >/dev/null 2>&1 \
    || { echo "error: neither 'kubectl' nor 'k3s' (which bundles it) found on PATH" >&2; missing=1; }
  docker info >/dev/null 2>&1 || { echo "error: cannot talk to the Docker daemon (is it running? are you in the 'docker' group?)" >&2; missing=1; }
  [ "$missing" -eq 0 ]
}

# ------------------------------------------------------------- config (.env) ---
# .env carries the SECRETS (and only those - see README "Where configuration
# lives"). Everything non-secret is read by the cluster from k8s/base/config.env.
# Prints one line per problem, returns non-zero if any is fatal.
validate_config() {
  local key val problems=0
  if [ ! -f .env ]; then
    echo "error: .env not found - copy .env.example to .env and set the REQUIRED values first" >&2
    return 1
  fi
  for key in GRAFANA_ADMIN_PASSWORD BACKEND_ADMIN_PASSWORD BACKEND_PLANNER_PASSWORD BACKEND_SESSION_SECRET; do
    val="$(file_value .env "$key")"
    if [ -z "$val" ]; then
      echo "error: $key is missing or empty in .env" >&2; problems=1
    elif [ "$ENV_NAME" = prod ] && [[ "$val" == changeme* ]]; then
      # local may keep the example placeholders (nothing is reachable off-host);
      # prod is internet-facing, so a placeholder credential is a hard error.
      echo "error: $key still has the .env.example placeholder - set a real value for prod" >&2; problems=1
    fi
  done
  if [ "$ENV_NAME" = prod ]; then
    val="$(file_value .env BACKEND_SESSION_SECRET)"
    if [ -n "$val" ] && [ "${#val}" -lt 32 ]; then
      echo "error: BACKEND_SESSION_SECRET is shorter than 32 characters - use e.g. \`openssl rand -hex 32\`" >&2; problems=1
    fi
  fi

  # Drift: a key present in BOTH .env and k8s/base/config.env with different
  # values means .env is silently ignored on Kubernetes (it is only read for
  # the secrets above). Never fatal, but always worth saying out loud.
  local cfg_val env_val
  while IFS= read -r key; do
    grep -q "^${key}=" .env || continue
    env_val="$(file_value .env "$key")"; cfg_val="$(file_value k8s/base/config.env "$key")"
    if [ "$env_val" != "$cfg_val" ]; then
      warn ".env sets ${key}=${env_val} but the cluster reads k8s/base/config.env's ${key}=${cfg_val} - the .env value is IGNORED on Kubernetes; edit k8s/base/config.env to change it"
    fi
  done < <(grep -oE '^[A-Z][A-Z0-9_]*' k8s/base/config.env)

  [ "$problems" -eq 0 ]
}

# ------------------------------------------------------ cluster ownership ---
# local: this script owns the cluster's whole lifecycle (k3d makes it cheap and
#        disposable, and "clean slate" is the point of `down`).
# prod:  the cluster is long-lived host infrastructure that exists BEFORE and
#        AFTER this project (k3s, installed once by the operator). This script
#        only ever manages the iot-pipeline namespace inside it.
local_cluster_exists() { k3d cluster list "$LOCAL_CLUSTER_NAME" >/dev/null 2>&1; }

# Always point kubectl at an EXPLICIT kubeconfig, never the ambient one. D46:
# on a host with native k3s, `kubectl` silently defaults to
# /etc/rancher/k3s/k3s.yaml and ignores ~/.kube/config, so an unset
# KUBECONFIG quietly targets the wrong cluster. Prod pointing at the wrong
# cluster is far worse than local doing so, hence explicit in both.
use_cluster() {
  case "$ENV_NAME" in
    local)
      local_cluster_exists || die "no k3d cluster '$LOCAL_CLUSTER_NAME' - run: k8s/deploy.sh local up"
      KUBECONFIG="$(k3d kubeconfig write "$LOCAL_CLUSTER_NAME")"
      ;;
    prod)
      [ -r "$PROD_KUBECONFIG" ] || die "cannot read kubeconfig '$PROD_KUBECONFIG' (k3s writes it root-only: run as root/sudo, or copy it and set PROD_KUBECONFIG=<path>)"
      KUBECONFIG="$PROD_KUBECONFIG"
      ;;
  esac
  export KUBECONFIG
  if ! kctl get nodes >/dev/null 2>&1; then
    local hint=""
    [ "$ENV_NAME" != prod ] || hint=" (is k3s running? try: systemctl status k3s)"
    die "cannot reach the Kubernetes API using $KUBECONFIG$hint"
  fi
}

node_count() { kctl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' '; }

ensure_cluster() {
  case "$ENV_NAME" in
    local)
      if ! local_cluster_exists; then
        say "Creating k3d cluster '$LOCAL_CLUSTER_NAME'"
        # Maps host 8000/3000 through k3d's built-in serverlb to the cluster's
        # `backend`/`grafana` Services, which are type: LoadBalancer (see
        # k8s/base/deployment-backend.yaml, deployment-grafana.yaml) so k3d's
        # klipper servicelb binds these host ports to them - k3d's documented
        # pattern for exposing a Service without an Ingress controller.
        k3d cluster create "$LOCAL_CLUSTER_NAME" -p "8000:8000@loadbalancer" -p "3000:3000@loadbalancer"
      else
        say "Reusing existing k3d cluster '$LOCAL_CLUSTER_NAME'"
      fi
      use_cluster
      ;;
    prod)
      use_cluster
      say "Deploying to the PRODUCTION cluster at $(kctl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null) - $(node_count) node(s): $(kctl get nodes --no-headers -o custom-columns=NAME:.metadata.name | paste -sd, -)"
      # Images are loaded into THIS host's containerd only. On a multi-node
      # cluster a pod scheduled on another node would sit in ImagePullBackOff
      # (the manifests reference :local tags, not a registry). Multi-node needs
      # a registry + a prod Kustomize overlay - REQUIREMENTS.md "full P6".
      if [ "$(node_count)" -gt 1 ] && [ -z "${SKIP_IMAGE_LOAD:-}" ]; then
        die "this cluster has $(node_count) nodes but images are only loaded into this host. Multi-node needs a registry (not built yet, 'full P6'). If you deliver images yourself, re-run with SKIP_IMAGE_LOAD=1"
      fi
      ;;
  esac
}

# ---------------------------------------------------------------- images ---
image_ref() { echo "iu-sensor-pipeline/$1:local"; }

build_image() {
  local ref; ref="$(image_ref "$1")"
  case "$1" in
    backend)      docker build -t "$ref" -f backend/Dockerfile . ;;
    producer)     docker build -t "$ref" -f producer/Dockerfile producer ;;
    cassandra)    docker build -t "$ref" -f infra/cassandra/Dockerfile infra/cassandra ;;
    spark-job)    docker build -t "$ref" -f spark_job/Dockerfile spark_job ;;
    spark-worker) docker build -t "$ref" -f spark_job/worker.Dockerfile spark_job ;;
    grafana)
      local plugin_ver="${GRAFANA_CASSANDRA_PLUGIN_VERSION:-$(file_value .env GRAFANA_CASSANDRA_PLUGIN_VERSION)}"
      docker build -t "$ref" --build-arg "CASSANDRA_PLUGIN_VERSION=${plugin_ver:-3.3.0}" -f infra/grafana/Dockerfile infra/grafana ;;
    dataset-init) docker build -t "$ref" -f kaggle_repository/Dockerfile kaggle_repository ;;
    *) die "unknown service '$1' (valid: $SERVICES)" ;;
  esac
}

# Cluster nodes do not share the host's Docker image store, so a plain
# `docker build` is invisible to them. HOW an image gets in differs because the
# two clusters keep images in different places:
#   local: k3d nodes are Docker containers with their own store -> `k3d image import`
#   prod:  k3s runs its OWN containerd on the host, separate from Docker's
#          (docker ps is empty while k3s pods run) -> stream `docker save` into it
load_images() {
  local refs=() s
  for s in "$@"; do refs+=("$(image_ref "$s")"); done
  case "$ENV_NAME" in
    local) k3d image import "${refs[@]}" -c "$LOCAL_CLUSTER_NAME" ;;
    prod)  docker save "${refs[@]}" | $SUDO k3s ctr images import - ;;
  esac
}

# ------------------------------------------------------- shared deploy steps ---
# kustomize refuses to reference a file outside the kustomization root (k8s/base)
# as a security restriction, so the real source of truth (infra/) is mirrored
# into a gitignored k8s/base/generated/ before every apply. kustomization.yaml's
# configMapGenerator reads from there. Skipping this makes `kubectl apply -k`
# fail on a fresh clone.
stage_generated() {
  say "Staging config sources into k8s/base/generated"
  local gen="$ROOT_DIR/k8s/base/generated"
  rm -rf "$gen"
  mkdir -p "$gen/cassandra-schema" "$gen/grafana"
  cp infra/cassandra/schema/*.cql "$gen/cassandra-schema/"
  cp infra/prometheus/prometheus.yml "$gen/prometheus.yml"
  cp infra/loki/loki-config.yml "$gen/loki-config.yml"
  cp infra/promtail/promtail-config-k8s.yml "$gen/promtail-config-k8s.yml"
  cp infra/grafana/provisioning/datasources/datasources.yaml "$gen/grafana/"
  cp infra/grafana/provisioning/dashboards/dashboards.yaml "$gen/grafana/"
  cp infra/grafana/provisioning/dashboards/json/kpi-dashboard.json "$gen/grafana/"
  cp infra/grafana/provisioning/alerting/contactpoints.yaml "$gen/grafana/"
  cp infra/grafana/provisioning/alerting/policies.yaml "$gen/grafana/"
  cp infra/grafana/provisioning/alerting/rules.yaml "$gen/grafana/"
}

# The Secret is never committed; it is generated from .env at apply time.
# The namespace must exist first or `create secret` has nowhere to go.
apply_namespace_and_secret() {
  say "Applying namespace"
  kctl apply -f "$ROOT_DIR/k8s/base/namespace.yaml"

  say "Generating app-secrets Secret from .env"
  local kaggle_user kaggle_key
  kaggle_user="$(file_value .env KAGGLE_USERNAME)"; kaggle_key="$(file_value .env KAGGLE_KEY)"
  kctl create secret generic app-secrets \
    --namespace "$NAMESPACE" \
    --from-literal="GRAFANA_ADMIN_PASSWORD=$(file_value .env GRAFANA_ADMIN_PASSWORD)" \
    --from-literal="BACKEND_ADMIN_PASSWORD=$(file_value .env BACKEND_ADMIN_PASSWORD)" \
    --from-literal="BACKEND_PLANNER_PASSWORD=$(file_value .env BACKEND_PLANNER_PASSWORD)" \
    --from-literal="BACKEND_SESSION_SECRET=$(file_value .env BACKEND_SESSION_SECRET)" \
    --from-literal="KAGGLE_USERNAME=${kaggle_user}" \
    --from-literal="KAGGLE_KEY=${kaggle_key}" \
    --dry-run=client -o yaml | kctl apply -f -
}

# Best-effort by design: a pod that starts before a dependency is ready
# recovers on its own via its initContainer TCP-wait loop and normal restart
# backoff, so a slow wait is feedback, not a failure. The summary below is the
# real verdict.
wait_ready() {
  say "Waiting for cassandra and kafka to become ready (this can take a few minutes)"
  kctl -n "$NAMESPACE" rollout status statefulset/cassandra --timeout=300s || true
  kctl -n "$NAMESPACE" rollout status statefulset/kafka --timeout=180s || true

  say "Waiting for one-shot init Jobs"
  kctl -n "$NAMESPACE" wait --for=condition=complete --timeout=300s \
    job/kafka-topic-init job/cassandra-schema-init job/dataset-init || true

  say "Waiting for backend and grafana"
  kctl -n "$NAMESPACE" rollout status deployment/backend --timeout=300s || true
  kctl -n "$NAMESPACE" rollout status deployment/grafana --timeout=180s || true
}

print_verdict() {
  echo
  kctl -n "$NAMESPACE" get pods
  local bad
  bad="$(kctl -n "$NAMESPACE" get pods --no-headers | awk '{split($2,r,"/"); if ($3=="Completed") next; if ($3!="Running" || r[1]!=r[2]) print "  - " $1 " (" $2 " " $3 ")"}')"
  echo
  if [ -n "$bad" ]; then
    warn "not everything is Running/Completed yet:"
    echo "$bad" >&2
    echo "    Give it a few minutes, then: k8s/deploy.sh $ENV_NAME status" >&2
    echo "    Still stuck?  kubectl -n $NAMESPACE describe pod <name>   /   kubectl -n $NAMESPACE logs <name>" >&2
  else
    say "All pods Running/Completed."
  fi
}

print_urls() {
  local host
  case "$ENV_NAME" in
    local) host="localhost" ;;
    # servicelb binds these on the host's own interfaces; there is no Ingress/TLS
    # yet ('full P6'), so this is plain HTTP - see docs/deployment.html section 6.
    prod)  host="$(hostname -I 2>/dev/null | awk '{print $1}')"; host="${host:-<host-ip>}" ;;
  esac
  cat <<EOF

==> Backend:  http://${host}:8000
==> Grafana:  http://${host}:3000
==> Everything else (Spark UIs, Prometheus, ...) is cluster-internal only;
    reach it with: kubectl -n $NAMESPACE port-forward svc/<name> <port>
==> kafka-ui is off by default (memory budget): kubectl -n $NAMESPACE scale deployment kafka-ui --replicas=1
EOF
  if [ "$ENV_NAME" = prod ]; then
    echo "==> prod is plain HTTP until TLS is set up - see docs/deployment.html section 6."
  fi
}

# ---------------------------------------------------------------- commands ---
cmd_check() {
  local fails=0
  ok()   { echo "  [ ok ] $*"; }
  info() { echo "  [info] $*"; }
  bad()  { echo "  [FAIL] $*"; fails=$((fails + 1)); }
  say "Checking prerequisites for '$ENV_NAME' (nothing is changed)"

  check_tools && ok "required tools present and Docker daemon reachable" || bad "missing tools / Docker (see errors above)"
  validate_config && ok ".env has every required secret set" || bad ".env problems (see errors above)"

  case "$ENV_NAME" in
    local)
      if local_cluster_exists; then info "k3d cluster '$LOCAL_CLUSTER_NAME' already exists (up will reuse it)"
      else info "no k3d cluster yet (up will create it)"; fi
      ;;
    prod)
      if [ -r "$PROD_KUBECONFIG" ]; then ok "kubeconfig readable: $PROD_KUBECONFIG"; else bad "cannot read $PROD_KUBECONFIG (run as root/sudo, or set PROD_KUBECONFIG)"; fi
      if command -v systemctl >/dev/null 2>&1; then
        [ "$(systemctl is-active k3s 2>/dev/null)" = active ] && ok "k3s service is active" || bad "k3s service is not active (systemctl status k3s)"
        [ "$(systemctl is-enabled k3s 2>/dev/null)" = enabled ] && ok "k3s starts on boot" || warn "k3s is not enabled at boot - the stack will not survive a reboot"
      fi
      if [ -r "$PROD_KUBECONFIG" ] && ( KUBECONFIG="$PROD_KUBECONFIG" kctl get nodes >/dev/null 2>&1 ); then
        export KUBECONFIG="$PROD_KUBECONFIG"
        ok "Kubernetes API reachable, $(node_count) node(s)"
        if [ "$(node_count)" -gt 1 ]; then bad "multi-node cluster: images are only loaded into this host (see ensure_cluster)"; fi
        kctl get storageclass local-path >/dev/null 2>&1 && ok "StorageClass local-path exists (k8s/base/pvc.yaml needs it)" || bad "StorageClass local-path missing - every PVC would stay Pending"
        if kctl get ns "$NAMESPACE" >/dev/null 2>&1; then info "namespace $NAMESPACE already exists (up will update it in place)"; else info "namespace $NAMESPACE does not exist yet (up will create it)"; fi
        local have; have="$($SUDO k3s ctr images ls -q 2>/dev/null | grep -c 'iu-sensor-pipeline/' || true)"
        info "$have of $(echo $SERVICES | wc -w | tr -d ' ') custom images already in k3s containerd (up rebuilds and reloads all of them)"
      fi
      if command -v ufw >/dev/null 2>&1; then
        local ufw_state; ufw_state="$($SUDO ufw status 2>/dev/null | head -1 || true)"
        info "firewall: ${ufw_state:-unknown (ufw status needs root)} - confirm 8000/3000 (or your TLS proxy ports) are the only public ones"
      else
        warn "ufw not installed - see docs/deployment.html section 2 (hardening) before exposing this host"
      fi
      ;;
  esac
  echo
  if [ "$fails" -eq 0 ]; then say "check passed"; else die "$fails check(s) failed"; fi
}

cmd_up() {
  check_tools || die "prerequisites missing (run: k8s/deploy.sh $ENV_NAME check)"
  validate_config || die "fix .env (run: k8s/deploy.sh $ENV_NAME check)"
  ensure_cluster

  if [ -z "${SKIP_IMAGE_LOAD:-}" ]; then
    say "Building local images"
    local s
    for s in $SERVICES; do build_image "$s"; done
    say "Loading images into the $ENV_NAME cluster"
    # shellcheck disable=SC2086
    load_images $SERVICES
  else
    say "SKIP_IMAGE_LOAD set - not building or loading images"
  fi

  stage_generated
  apply_namespace_and_secret
  say "Applying k8s/base (kustomize)"
  kctl apply -k "$ROOT_DIR/k8s/base"
  wait_ready
  print_verdict
  print_urls
  cat <<EOF

==> Re-running 'up' is safe, but does NOT restart already-running pods with new code
    (their spec is unchanged, so Kubernetes sees nothing to do). After a code change:
      k8s/deploy.sh $ENV_NAME update <service>...     (services: $SERVICES)
EOF
}

# Why `update` exists at all: images are tagged :local. Rebuilding and
# re-importing under the same tag is not a change Kubernetes can see in the pod
# spec, so `kubectl apply` alone leaves the OLD container running. An explicit
# rollout restart is what makes the new image live. This holds identically in
# local and prod.
cmd_update() {
  [ $# -gt 0 ] || die "usage: k8s/deploy.sh $ENV_NAME update <service>...   (services: $SERVICES)"
  local s
  for s in "$@"; do
    case " $SERVICES " in *" $s "*) ;; *) die "unknown service '$s' (valid: $SERVICES)" ;; esac
  done
  check_tools || die "prerequisites missing (run: k8s/deploy.sh $ENV_NAME check)"
  use_cluster
  [ "$ENV_NAME" = local ] || [ "$(node_count)" -le 1 ] || die "multi-node cluster: images are only loaded into this host (see ensure_cluster)"

  for s in "$@"; do say "Building $s"; build_image "$s"; done
  say "Loading into the $ENV_NAME cluster"
  load_images "$@"

  for s in "$@"; do
    case "$s" in
      cassandra)
        warn "restarting the cassandra StatefulSet restarts the database; pods restart one at a time"
        kctl -n "$NAMESPACE" rollout restart statefulset/cassandra
        kctl -n "$NAMESPACE" rollout status statefulset/cassandra --timeout=600s ;;
      dataset-init)
        # A Job's pod template is immutable; it is a one-shot that skips the
        # download once the file exists, so there is nothing running to restart.
        say "dataset-init is a one-shot Job: image reloaded, nothing to restart. To re-run it: kubectl -n $NAMESPACE delete job dataset-init && k8s/deploy.sh $ENV_NAME up" ;;
      *)
        kctl -n "$NAMESPACE" rollout restart "deployment/$s"
        kctl -n "$NAMESPACE" rollout status "deployment/$s" --timeout=300s ;;
    esac
  done
}

cmd_status() {
  use_cluster
  kctl -n "$NAMESPACE" get pods,pvc,svc
}

cmd_down() {
  local assume_yes=""
  [ "${1:-}" != "--yes" ] || assume_yes=1

  case "$ENV_NAME" in
    local)
      # Deleting the cluster deletes every PVC's backing data with it - the k3d
      # equivalent of `docker compose down -v`. It is a disposable dev cluster
      # created by this script, so no confirmation.
      command -v k3d >/dev/null 2>&1 || die "'k3d' not found on PATH"
      if local_cluster_exists; then
        say "Deleting k3d cluster '$LOCAL_CLUSTER_NAME'"
        k3d cluster delete "$LOCAL_CLUSTER_NAME"
      else
        say "No k3d cluster named '$LOCAL_CLUSTER_NAME' found, nothing to do"
      fi
      # D46/D47: `k3d cluster delete` spins up its own `k3d-<name>-tools`
      # helper for volume/network cleanup but doesn't reliably stop it before
      # removing the network/volume it is attached to (observed live, k3d
      # v5.9.0). That container runs `noop` forever, so without this the
      # container/network/volume accumulate silently on every run.
      docker rm -f "k3d-${LOCAL_CLUSTER_NAME}-tools" >/dev/null 2>&1 || true
      docker network rm "k3d-${LOCAL_CLUSTER_NAME}" >/dev/null 2>&1 || true
      docker volume rm "k3d-${LOCAL_CLUSTER_NAME}-images" >/dev/null 2>&1 || true
      ;;
    prod)
      # Prod's cluster outlives this project and may run other workloads, so
      # `down` removes only our namespace - never k3s. The namespace holds the
      # only copy of the sensor history (Cassandra PVCs), and deleting it is
      # irreversible, so it is gated behind an explicit confirmation.
      use_cluster
      if ! kctl get ns "$NAMESPACE" >/dev/null 2>&1; then
        say "Namespace $NAMESPACE does not exist, nothing to do"
        return 0
      fi
      echo "This will PERMANENTLY DELETE namespace '$NAMESPACE' on the PRODUCTION cluster,"
      echo "including every PersistentVolumeClaim below and all data on them:"
      kctl -n "$NAMESPACE" get pvc --no-headers -o custom-columns=NAME:.metadata.name,SIZE:.spec.resources.requests.storage | sed 's/^/    /'
      if [ -z "$assume_yes" ]; then
        [ -t 0 ] || die "refusing to delete without a terminal; pass --yes to confirm non-interactively"
        local reply
        read -r -p "Type the namespace name ($NAMESPACE) to confirm: " reply
        [ "$reply" = "$NAMESPACE" ] || die "confirmation did not match - nothing deleted"
      fi
      say "Deleting namespace $NAMESPACE"
      kctl delete ns "$NAMESPACE" --wait=true --timeout=180s
      cat <<EOF

==> Done. k3s itself is untouched. Not removed (by design):
      - custom images in k3s containerd:   $SUDO k3s crictl rmi <image>   (optional)
      - Docker's image/build cache:        docker system prune -a          (optional)
    Verify the PVC data is gone:           du -sh /var/lib/rancher/k3s/storage
EOF
      ;;
  esac
}

case "$COMMAND" in
  check)  cmd_check ;;
  up)     cmd_up ;;
  update) cmd_update "$@" ;;
  status) cmd_status ;;
  down)   cmd_down "$@" ;;
  *) echo "error: unknown command '$COMMAND'" >&2; usage ;;
esac
