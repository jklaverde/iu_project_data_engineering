import asyncio

from fastapi import APIRouter, HTTPException, Request, status

# D42 (FR-N1/N2) - admin-only (require_admin dependency wired in main.py, same
# as admin.alerts_router). Separate from admin.py since this is Cassandra
# ring/storage-specific, not alert plumbing.
router = APIRouter(prefix="/api/admin/cassandra", tags=["admin"])


@router.get("/storage")
async def cassandra_storage(request: Request):
    nodes = request.app.state.cassandra_nodes
    return await asyncio.to_thread(nodes.storage_summary_sync)


@router.post("/nodes")
async def deploy_cassandra_node(request: Request):
    """FR-N2: kicks off the create -> healthy -> join-the-ring sequence as a
    background task and returns immediately - the whole thing can take
    several minutes (Cassandra bootstrap streaming), far longer than a
    request should block. Progress is pushed over the pipeline-state
    WebSocket channel (see CassandraNodes.deploy_node)."""
    if getattr(request.app.state, "cassandra_deploy_in_progress", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "A node deploy is already in progress")

    nodes = request.app.state.cassandra_nodes
    ws_manager = request.app.state.ws_manager

    async def run():
        request.app.state.cassandra_deploy_in_progress = True
        try:
            await nodes.deploy_node(ws_manager)
        finally:
            request.app.state.cassandra_deploy_in_progress = False

    asyncio.create_task(run())
    return {"status": "started"}
