import asyncio

from fastapi import APIRouter, HTTPException, Request, status

from ..cassandra_nodes import KubernetesUnavailableError

# D42/D43 (FR-N1/N2, FR-K1) - admin-only (require_admin dependency wired in
# main.py, same as admin.alerts_router). Separate from admin.py since this is
# Cassandra ring/storage/Kubernetes-specific, not alert plumbing.
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/cassandra/storage")
async def cassandra_storage(request: Request):
    nodes = request.app.state.cassandra_nodes
    try:
        return await asyncio.to_thread(nodes.storage_summary_sync)
    except KubernetesUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.post("/cassandra/nodes")
async def deploy_cassandra_node(request: Request):
    """FR-N2: kicks off the scale -> healthy -> join-the-ring sequence as a
    background task and returns immediately - the whole thing can take
    several minutes (Cassandra bootstrap streaming), far longer than a
    request should block. Progress is pushed over the pipeline-state
    WebSocket channel (see CassandraNodes.deploy_node)."""
    if getattr(request.app.state, "cassandra_deploy_in_progress", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "A node deploy is already in progress")

    nodes = request.app.state.cassandra_nodes
    if not nodes._available:  # noqa: SLF001 - cheap availability check, avoid starting a doomed background task
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Kubernetes API not available")

    ws_manager = request.app.state.ws_manager

    async def run():
        request.app.state.cassandra_deploy_in_progress = True
        try:
            await nodes.deploy_node(ws_manager)
        finally:
            request.app.state.cassandra_deploy_in_progress = False

    asyncio.create_task(run())
    return {"status": "started"}


@router.get("/kubernetes/status")
async def kubernetes_status(request: Request):
    """FR-K1 (D43, UC-13): pod + StatefulSet/Deployment status for the admin
    Kubernetes-status panel, via the same RBAC-scoped client FR-N1/FR-N3
    already use."""
    nodes = request.app.state.cassandra_nodes
    try:
        return await asyncio.to_thread(nodes.cluster_status_sync)
    except KubernetesUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
