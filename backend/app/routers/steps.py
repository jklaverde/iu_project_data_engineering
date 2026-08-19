from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["steps"])

VALID_STEPS = {"deployment", "ingestion", "kafka", "spark", "cassandra", "summary"}


@router.get("/pipeline-state")
async def pipeline_state(request: Request):
    return await request.app.state.poller.get_snapshot()


@router.get("/steps/{name}")
async def step(name: str, request: Request):
    if name not in VALID_STEPS:
        raise HTTPException(status_code=404, detail=f"Unknown step: {name}")
    snapshot = await request.app.state.poller.get_snapshot()
    return snapshot.get(name)
