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
