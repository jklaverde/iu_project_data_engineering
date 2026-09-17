import asyncio
import json
import logging
import re
import time

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream as k8s_stream

from .ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

# D43 (§4.4): fixed rather than configurable - this project runs one
# namespace, one StatefulSet, matching the k8s/base/ manifests exactly.
# There is no reason to let these drift from each other via config.
NAMESPACE = "iot-pipeline"
STATEFULSET_NAME = "cassandra"
APP_LABEL_SELECTOR = "app=cassandra"

NODETOOL_ROW_RE = re.compile(
    r"^(?P<status>[UD][NLJM])\s+(?P<address>\S+)\s+(?P<load>[\d.]+\s*\S+)\s+"
)
_LOAD_UNITS = {"bytes": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}

HEALTHY_TIMEOUT_SECONDS = 240
RING_JOIN_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 5
EXEC_TIMEOUT_SECONDS = 30


class NodeDeployError(Exception):
    pass


class KubernetesUnavailableError(Exception):
    """Raised instead of crashing the app (D43): this backend image also
    still runs under the historical docker-compose.yml, which has no
    ServiceAccount to mount - load_incluster_config() fails there by
    design, and every Cassandra-scaling/status endpoint should degrade to
    a clear 503 rather than take the whole app down with it."""


def _parse_load_bytes(text: str) -> int:
    value, unit = text.strip().split()
    return int(float(value) * _LOAD_UNITS.get(unit.lower(), 1))


def _parse_nodetool_status(output: str) -> list[dict]:
    rows = []
    for line in output.splitlines():
        m = NODETOOL_ROW_RE.match(line.strip())
        if m:
            rows.append({
                "status": m.group("status"),
                "address": m.group("address"),
                "load_bytes": _parse_load_bytes(m.group("load")),
            })
    return rows


def _pod_ordinal(pod_name: str) -> int | None:
    try:
        return int(pod_name.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


class CassandraNodes:
    """Kubernetes-API-backed Cassandra ring operations for D42/D43
    (FR-N1-N4, FR-K1). Replaces the D42 Docker-socket approach entirely -
    scaling the `cassandra` StatefulSet and exec'ing into its pods via a
    narrowly-scoped RBAC Role (NFR-16) instead of host-root-equivalent
    Docker access (closes R-9)."""

    def __init__(self, storage_budget_bytes: int):
        self._budget = storage_budget_bytes
        self._available = False
        self._core_v1: k8s_client.CoreV1Api | None = None
        self._apps_v1: k8s_client.AppsV1Api | None = None
        try:
            k8s_config.load_incluster_config()
            self._core_v1 = k8s_client.CoreV1Api()
            self._apps_v1 = k8s_client.AppsV1Api()
            self._available = True
        except Exception as exc:
            logger.warning(json.dumps({
                "event": "kubernetes_unavailable",
                "detail": "load_incluster_config failed - Cassandra-scaling/status endpoints will 503. "
                           "Expected when running under the historical docker-compose.yml (D43).",
                "error": str(exc),
            }))

    def _require_available(self) -> None:
        if not self._available:
            raise KubernetesUnavailableError("Kubernetes API not available (no in-cluster config)")

    # -- low-level exec, replacing docker.Container.exec_run ----------------

    def _exec_sync(self, pod_name: str, command: list[str]) -> tuple[bool, str]:
        resp = k8s_stream(
            self._core_v1.connect_get_namespaced_pod_exec,
            pod_name, NAMESPACE,
            command=command, stderr=True, stdin=False, stdout=True, tty=False,
            _preload_content=False,
        )
        resp.run_forever(timeout=EXEC_TIMEOUT_SECONDS)
        stdout = resp.read_stdout() or ""
        success = True
        err_channel = resp.read_channel(3)  # ERROR_CHANNEL - carries exec exit status as JSON
        if err_channel:
            try:
                success = json.loads(err_channel).get("status") == "Success"
            except (json.JSONDecodeError, AttributeError):
                success = False
        resp.close()
        return success, stdout

    # -- pod/StatefulSet inspection -----------------------------------------

    def _list_cassandra_pods(self):
        return self._core_v1.list_namespaced_pod(NAMESPACE, label_selector=APP_LABEL_SELECTOR).items

    def _current_replicas(self) -> int:
        sts = self._apps_v1.read_namespaced_stateful_set(STATEFULSET_NAME, NAMESPACE)
        return sts.spec.replicas

    def storage_summary_sync(self) -> dict:
        """FR-N1: nodetool status (exec'd via the Kubernetes API into
        cassandra-0) reports every ring member's Load in one shot - more
        robust than a Prometheus metric, which would need a scrape-config
        change every time a node is added (infra/prometheus/prometheus.yml
        has a static target list, confirmed while scoping D42)."""
        self._require_available()
        success, output = self._exec_sync("cassandra-0", ["nodetool", "status"])
        if not success:
            raise NodeDeployError(f"nodetool status failed: {output}")
        rows = _parse_nodetool_status(output)

        pods_by_ip = {p.status.pod_ip: p.metadata.name for p in self._list_cassandra_pods() if p.status.pod_ip}
        nodes = [
            {
                "container_name": pods_by_ip.get(row["address"], row["address"]),
                "address": row["address"],
                "load_bytes": row["load_bytes"],
                "percent_of_budget": round(100 * row["load_bytes"] / self._budget, 1),
                "up_normal": row["status"] == "UN",
            }
            for row in rows
        ]
        return {"budget_bytes": self._budget, "nodes": nodes}

    def discover_extra_nodes_health_sync(self) -> list[dict]:
        """FR-N3: the deployment grid discovers any cassandra-N (N >= 1)
        pods beyond the StatefulSet's original first replica - StatefulSet
        pod naming is deterministic and ordinal, so no more container-name
        prefix matching is needed the way D42's Docker version required."""
        self._require_available()
        result = []
        for pod in self._list_cassandra_pods():
            ordinal = _pod_ordinal(pod.metadata.name)
            if ordinal is None or ordinal == 0:
                continue
            container_statuses = pod.status.container_statuses or []
            ready = bool(container_statuses) and all(c.ready for c in container_statuses)
            detail = pod.status.phase
            if container_statuses and container_statuses[0].state.waiting:
                detail = container_statuses[0].state.waiting.reason or detail
            result.append({
                "name": pod.metadata.name,
                "healthy": ready,
                "detail": detail,
                "latency_ms": None,
            })
        return result

    def cluster_status_sync(self) -> dict:
        """FR-K1: pod + StatefulSet/Deployment status for the admin
        Kubernetes-status panel (UC-13) - read-only, same RBAC grant as
        FR-N1/FR-N3."""
        self._require_available()
        pods = self._core_v1.list_namespaced_pod(NAMESPACE).items
        pod_summaries = []
        for pod in pods:
            container_statuses = pod.status.container_statuses or []
            restarts = sum(c.restart_count for c in container_statuses)
            ready_count = sum(1 for c in container_statuses if c.ready)
            pod_summaries.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready": f"{ready_count}/{len(container_statuses)}",
                "restarts": restarts,
                "node": pod.spec.node_name,
            })

        workloads = []
        for sts in self._apps_v1.list_namespaced_stateful_set(NAMESPACE).items:
            workloads.append({
                "kind": "StatefulSet", "name": sts.metadata.name,
                "desired": sts.spec.replicas, "ready": sts.status.ready_replicas or 0,
            })
        for dep in self._apps_v1.list_namespaced_deployment(NAMESPACE).items:
            workloads.append({
                "kind": "Deployment", "name": dep.metadata.name,
                "desired": dep.spec.replicas, "ready": dep.status.ready_replicas or 0,
            })

        return {"pods": pod_summaries, "workloads": workloads}

    # -- node-deploy orchestration (FR-N2) -----------------------------------

    def _scale_statefulset_sync(self, replicas: int) -> None:
        self._apps_v1.patch_namespaced_stateful_set_scale(
            STATEFULSET_NAME, NAMESPACE, {"spec": {"replicas": replicas}}
        )

    def _wait_pod_ready_sync(self, pod_name: str) -> None:
        deadline = time.monotonic() + HEALTHY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                pod = self._core_v1.read_namespaced_pod_status(pod_name, NAMESPACE)
            except ApiException as exc:
                if exc.status == 404:
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                raise NodeDeployError(f"could not read pod status: {exc.reason}") from exc

            statuses = pod.status.container_statuses or []
            for c in statuses:
                waiting = c.state.waiting
                if waiting and waiting.reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                    raise NodeDeployError(f"pod {pod_name} is stuck: {waiting.reason} ({waiting.message or 'no message'})")
            if pod.status.phase == "Failed":
                raise NodeDeployError(f"pod {pod_name} failed to start: {pod.status.reason or pod.status.phase}")
            if statuses and all(c.ready for c in statuses):
                return
            time.sleep(POLL_INTERVAL_SECONDS)
        raise NodeDeployError(
            f"pod {pod_name} did not become ready within {HEALTHY_TIMEOUT_SECONDS}s - if this is an "
            "OOMKilled/Pending loop, the cluster likely doesn't have enough allocatable memory for a "
            "second Cassandra pod (see the Operations doc's known resource-contention note)"
        )

    def _pod_ip_sync(self, pod_name: str) -> str:
        pod = self._core_v1.read_namespaced_pod_status(pod_name, NAMESPACE)
        if not pod.status.pod_ip:
            raise NodeDeployError(f"pod {pod_name} has no IP yet")
        return pod.status.pod_ip

    def _wait_ring_join_sync(self, pod_ip: str) -> None:
        deadline = time.monotonic() + RING_JOIN_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            success, output = self._exec_sync("cassandra-0", ["nodetool", "status"])
            if success:
                rows = _parse_nodetool_status(output)
                if any(r["address"] == pod_ip and r["status"] == "UN" for r in rows):
                    return
            time.sleep(POLL_INTERVAL_SECONDS)
        raise NodeDeployError(f"node did not join the ring within {RING_JOIN_TIMEOUT_SECONDS}s")

    async def deploy_node(self, ws_manager: ConnectionManager) -> None:
        """FR-N2: scale the cassandra StatefulSet by one -> wait for the new
        pod ready -> wait for it to join the ring, broadcasting a step
        transition at the start/end of each phase (not per poll tick - the
        frontend animates continuously while a step is in_progress, same
        convention as PipelineFlowDiagram's CSS-driven particle loop, D26)."""

        current_step = "creating"

        async def emit(step: str, status: str, **extra):
            nonlocal current_step
            current_step = step
            await ws_manager.broadcast({"type": "cassandra-node-deploy", "step": step, "status": status, **extra})

        name = None
        try:
            self._require_available()
            current = await asyncio.to_thread(self._current_replicas)
            new_replicas = current + 1
            name = f"cassandra-{new_replicas - 1}"

            await emit("creating", "in_progress", node_name=name)
            await asyncio.to_thread(self._scale_statefulset_sync, new_replicas)
            await emit("creating", "done", node_name=name)

            await emit("healthy", "in_progress", node_name=name)
            await asyncio.to_thread(self._wait_pod_ready_sync, name)
            await emit("healthy", "done", node_name=name)

            await emit("joining_ring", "in_progress", node_name=name)
            pod_ip = await asyncio.to_thread(self._pod_ip_sync, name)
            await asyncio.to_thread(self._wait_ring_join_sync, pod_ip)
            await emit("joining_ring", "done", node_name=name)

            await emit("done", "done", node_name=name)
            logger.info(json.dumps({"event": "cassandra_node_deployed", "node_name": name}))
        except Exception as exc:
            logger.exception(json.dumps({"event": "cassandra_node_deploy_failed", "node_name": name}))
            # Marks whichever real step (creating/healthy/joining_ring) was
            # in flight as the one that failed - "error" is a status, not a
            # step of its own, so the animation's 4 boxes (which don't have
            # a 5th "error" box) can highlight the right one instead of
            # matching nothing and silently staying on "waiting" (a real bug
            # caught live-testing D42: the frontend used to receive
            # step="error" literally, which isn't in its STEPS list).
            await ws_manager.broadcast({
                "type": "cassandra-node-deploy", "step": current_step, "status": "error",
                "node_name": name, "message": str(exc),
            })
