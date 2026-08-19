import asyncio

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["anomalies"])


@router.get("/anomalies")
async def anomalies(request: Request, device_id: str | None = None, since_minutes: int = 60, limit: int = 100):
    reader = request.app.state.cassandra_reader
    rows = await asyncio.to_thread(reader.anomalies_sync, device_id, since_minutes, limit)
    return {"anomalies": rows}
