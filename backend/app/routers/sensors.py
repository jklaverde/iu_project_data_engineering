import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from .. import environment

router = APIRouter(prefix="/api", tags=["sensors"])


@router.get("/sensors")
async def sensors(request: Request):
    reader = request.app.state.cassandra_reader
    metadata, thresholds = await asyncio.gather(
        asyncio.to_thread(reader.device_metadata_sync),
        asyncio.to_thread(reader.device_thresholds_sync),
    )
    readings = await asyncio.gather(
        *(asyncio.to_thread(reader.latest_reading_sync, m["device_id"]) for m in metadata)
    )

    out = []
    for meta, reading in zip(metadata, readings):
        device_thresholds = thresholds.get(meta["device_id"], {})
        entry = {**meta, "reading": reading}
        if reading is None:
            entry["status"] = {"overall": "unknown", "reason": "no data yet", "metrics": {}}
            entry["air_quality_score"] = None
            entry["comfort_index"] = None
        else:
            entry["status"] = environment.device_status(reading, device_thresholds)
            entry["air_quality_score"] = environment.air_quality_score(reading, device_thresholds)
            entry["comfort_index"] = environment.comfort_index(reading.get("temp"), reading.get("humidity"))
        out.append(entry)

    return {"sensors": out}


@router.get("/sensors/{device_id}/history")
async def sensor_history(request: Request, device_id: str, granularity: str = "1h", hours: float = 24.0, limit: int = 200):
    if granularity not in ("1m", "1h"):
        granularity = "1h"
    reader = request.app.state.cassandra_reader

    rows = await asyncio.to_thread(reader.aggregates_sync, device_id, granularity, hours * 2, limit * 2)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent_rows = [r for r in rows if (r["window_start"] or "") >= cutoff][:limit]
    previous_rows = [r for r in rows if (r["window_start"] or "") < cutoff]

    recent_ratio = environment.chronic_exposure_ratio(recent_rows)
    previous_ratio = environment.chronic_exposure_ratio(previous_rows)

    return {
        "device_id": device_id,
        "granularity": granularity,
        "windows": recent_rows,
        "chronic_exposure_ratio": recent_ratio,
        "trend": environment.trend_direction(recent_ratio, previous_ratio),
    }
