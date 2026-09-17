#!/usr/bin/env bash
# Tears down the local k3d cluster created by k8s/local-up.sh. This deletes
# the whole cluster (and every PVC's backing local-path data with it) - the
# k3d equivalent of `docker compose down -v`, not `docker compose down`.
set -euo pipefail

CLUSTER_NAME="iot-pipeline"

command -v k3d >/dev/null 2>&1 || { echo "error: k3d not found on PATH" >&2; exit 1; }

if k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  echo "==> Deleting k3d cluster '$CLUSTER_NAME'"
  k3d cluster delete "$CLUSTER_NAME"
else
  echo "==> No k3d cluster named '$CLUSTER_NAME' found, nothing to do"
fi

# D46: k3d cluster delete spins up its own `k3d-<name>-tools` helper
# container for volume/network cleanup, but doesn't reliably stop it before
# trying to remove the network/volume that container is itself attached to
# - a real ordering issue observed live (k3d v5.9.0), not a leftover from a
# prior run. That container runs `noop` forever and never exits on its own,
# so without this, a re-run of local-up.sh reuses none of it (its own
# cluster is genuinely gone) but the orphaned container/network/volume just
# accumulate silently. Force-remove them so this script actually leaves a
# clean slate, matching its own `down -v` framing above.
docker rm -f "k3d-${CLUSTER_NAME}-tools" >/dev/null 2>&1 || true
docker network rm "k3d-${CLUSTER_NAME}" >/dev/null 2>&1 || true
docker volume rm "k3d-${CLUSTER_NAME}-images" >/dev/null 2>&1 || true
