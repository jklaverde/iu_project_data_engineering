import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Request

# Dataset Explorer (D38, FR-P2, FR-W8) - reachable by both roles, unlike the
# admin-only docs.router, since planners use it too for historical comparison
# (D39). Prefixed separately from /api/sensors: this reads the source CSV
# directly, never Kafka/Spark/Cassandra.
router = APIRouter(prefix="/api/dataset", tags=["dataset"])


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/summary")
async def dataset_summary(request: Request):
    reader = request.app.state.dataset_reader
    return await asyncio.to_thread(reader.summary)


@router.get("/readings")
async def dataset_readings(
    request: Request,
    device_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 500,
):
    reader = request.app.state.dataset_reader
    limit = max(1, min(limit, 5000))
    rows = await asyncio.to_thread(reader.query, device_id, _parse_dt(since), _parse_dt(until), limit)
    return {"readings": rows}
