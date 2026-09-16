import asyncio
import json
import logging
import re
import time

import docker

from .ws_manager import ConnectionManager

logger = logging.getLogger(__name__)

COMPOSE_SERVICE_LABEL = "com.docker.compose.service"
PRIMARY_SERVICE_NAME = "cassandra"
NODE_NAME_PREFIX = "cassandra-node-"
NODETOOL_ROW_RE = re.compile(
    r"^(?P<status>[UD][NLJM])\s+(?P<address>\S+)\s+(?P<load>[\d.]+\s*\S+)\s+"
)
_LOAD_UNITS = {"bytes": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}

HEALTHY_TIMEOUT_SECONDS = 240
RING_JOIN_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 5


class NodeDeployError(Exception):
    pass


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


class CassandraNodes:
    """Docker-Engine-API-backed Cassandra ring operations for D42 (FR-N1-N4).
    Talks to the mounted /var/run/docker.sock (NFR-15) rather than the
    compose CLI - creating a container this way needs no project files
    mounted into the backend, only the socket."""

    def __init__(self, storage_budget_bytes: int):
        self._budget = storage_budget_bytes
        self._client: docker.DockerClient | None = None

    def _docker(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _primary_container(self):
        client = self._docker()
        matches = client.containers.list(filters={"label": f"{COMPOSE_SERVICE_LABEL}={PRIMARY_SERVICE_NAME}"})
        if not matches:
            raise NodeDeployError("no running primary Cassandra container found")
        return matches[0]

    def _extra_node_containers(self):
        client = self._docker()
        return [c for c in client.containers.list(all=True) if c.name.startswith(NODE_NAME_PREFIX)]

    def _network_name(self, primary) -> str:
        networks = primary.attrs["NetworkSettings"]["Networks"]
        return next(iter(networks))

    def _container_names_by_ip(self, network_name: str) -> dict[str, str]:
        client = self._docker()
        result = {}
        for c in client.containers.list():
            net = c.attrs.get("NetworkSettings", {}).get("Networks", {}).get(network_name)
            if net and net.get("IPAddress"):
                result[net["IPAddress"]] = c.name
        return result

    def storage_summary_sync(self) -> dict:
        """FR-N1: nodetool status reports every ring member's Load in one
        shot - more robust than a Prometheus metric, which would need a
        scrape-config change every time a node is added (infra/prometheus/
        prometheus.yml has a static target list, confirmed while scoping D42)."""
        primary = self._primary_container()
        network_name = self._network_name(primary)
        names_by_ip = self._container_names_by_ip(network_name)

        exit_code, output = primary.exec_run("nodetool status")
        if exit_code != 0:
            raise NodeDeployError(f"nodetool status failed: {output.decode(errors='replace')}")
        rows = _parse_nodetool_status(output.decode(errors="replace"))

        nodes = [
            {
                "container_name": names_by_ip.get(row["address"], row["address"]),
                "address": row["address"],
                "load_bytes": row["load_bytes"],
                "percent_of_budget": round(100 * row["load_bytes"] / self._budget, 1),
                "up_normal": row["status"] == "UN",
            }
            for row in rows
        ]
        return {"budget_bytes": self._budget, "nodes": nodes}

    def discover_extra_nodes_health_sync(self) -> list[dict]:
        """FR-N3: the deployment grid discovers any extra cassandra-node-*
        containers this action has created, beyond the fixed configured
        service list state_poller.py already checks."""
        result = []
        for c in self._extra_node_containers():
            health = c.attrs.get("State", {}).get("Health", {}).get("Status")
            running = c.attrs.get("State", {}).get("Status") == "running"
            result.append({
                "name": c.name,
                "healthy": health == "healthy",
                "detail": health or c.attrs.get("State", {}).get("Status", "unknown"),
                "latency_ms": None,
            })
        return result

    def _next_node_name(self) -> str:
        existing = {c.name for c in self._extra_node_containers()}
        i = 1
        while f"{NODE_NAME_PREFIX}{i}" in existing:
            i += 1
        return f"{NODE_NAME_PREFIX}{i}"

    def _create_and_start_sync(self, primary, name: str):
        client = self._docker()
        network_name = self._network_name(primary)
        image = primary.attrs["Config"]["Image"]
        env = [e for e in primary.attrs["Config"]["Env"] if not e.startswith("CASSANDRA_SEEDS=")]
        env.append(f"CASSANDRA_SEEDS={PRIMARY_SERVICE_NAME}")
        hc = primary.attrs["Config"]["Healthcheck"] or {}
        healthcheck = {
            "test": hc.get("Test", []),
            "interval": hc.get("Interval", 15_000_000_000),
            "timeout": hc.get("Timeout", 10_000_000_000),
            "retries": hc.get("Retries", 10),
            "start_period": hc.get("StartPeriod", 60_000_000_000),
        }
        client.volumes.create(name=f"{name}-data")
        # No port bindings on purpose - the primary already publishes 9042/7070
        # on the host, a second container publishing the same ports would
        # collide. This node is reachable only on the internal Docker network,
        # which is all a ring member needs (§4.3).
        container = client.containers.run(
            image,
            name=name,
            hostname=name,
            environment=env,
            healthcheck=healthcheck,
            network=network_name,
            volumes={f"{name}-data": {"bind": "/var/lib/cassandra", "mode": "rw"}},
            mem_limit=primary.attrs["HostConfig"].get("Memory") or "2g",
            detach=True,
        )
        return container

    def _wait_healthy_sync(self, container) -> None:
        deadline = time.monotonic() + HEALTHY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            container.reload()
            state = container.attrs["State"]
            if state.get("Status") != "running":
                raise NodeDeployError(f"container exited: {state.get('Status')} ({state.get('Error') or 'no error message'})")
            if state.get("Health", {}).get("Status") == "healthy":
                return
            time.sleep(POLL_INTERVAL_SECONDS)
        raise NodeDeployError(f"container did not become healthy within {HEALTHY_TIMEOUT_SECONDS}s")

    def _wait_ring_join_sync(self, primary, container, network_name: str) -> None:
        container.reload()
        ip = container.attrs["NetworkSettings"]["Networks"][network_name]["IPAddress"]
        deadline = time.monotonic() + RING_JOIN_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            exit_code, output = primary.exec_run("nodetool status")
            if exit_code == 0:
                rows = _parse_nodetool_status(output.decode(errors="replace"))
                if any(r["address"] == ip and r["status"] == "UN" for r in rows):
                    return
            time.sleep(POLL_INTERVAL_SECONDS)
        raise NodeDeployError(f"node did not join the ring within {RING_JOIN_TIMEOUT_SECONDS}s")

    async def deploy_node(self, ws_manager: ConnectionManager) -> None:
        """FR-N2: the whole create -> healthy -> join-the-ring sequence,
        broadcasting a step transition at the start and end of each phase
        (not per poll tick - the frontend animates continuously while a step
        is in_progress, same convention as PipelineFlowDiagram's CSS-driven
        particle loop, D26)."""

        current_step = "creating"

        async def emit(step: str, status: str, **extra):
            nonlocal current_step
            current_step = step
            await ws_manager.broadcast({"type": "cassandra-node-deploy", "step": step, "status": status, **extra})

        name = None
        try:
            primary = await asyncio.to_thread(self._primary_container)
            name = await asyncio.to_thread(self._next_node_name)
            await emit("creating", "in_progress", node_name=name)
            container = await asyncio.to_thread(self._create_and_start_sync, primary, name)
            await emit("creating", "done", node_name=name)

            await emit("healthy", "in_progress", node_name=name)
            await asyncio.to_thread(self._wait_healthy_sync, container)
            await emit("healthy", "done", node_name=name)

            await emit("joining_ring", "in_progress", node_name=name)
            network_name = await asyncio.to_thread(self._network_name, primary)
            await asyncio.to_thread(self._wait_ring_join_sync, primary, container, network_name)
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
            # caught live-testing this: the frontend used to receive
            # step="error" literally, which isn't in its STEPS list).
            await ws_manager.broadcast({
                "type": "cassandra-node-deploy", "step": current_step, "status": "error",
                "node_name": name, "message": str(exc),
            })
