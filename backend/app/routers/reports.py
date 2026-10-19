import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from .. import environment, reports
from ..report_xlsx import extract_workbook, monthly_workbook

# Environmental officer reports (D55, UC-15-UC-18). Reachable by both roles
# (FR-R4), like /api/sensors. All computed on request from agg_1h (FR-O10).
router = APIRouter(prefix="/api/reports", tags=["reports"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_month(raw: str | None) -> tuple[int, int]:
    if not raw:
        local = reports.to_local(_now())
        return reports.shift_month(local.year, local.month, -1)  # last complete month
    try:
        year, month = (int(p) for p in raw.split("-"))
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Month must look like 2026-09.") from None
    return year, month


def _parse_day(raw: str, name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, f"The {name} date must look like 2026-09-30.") from None


def _local_period(start: str, end: str, max_days: int) -> tuple[datetime, datetime, date, date]:
    """Inclusive local dates -> [start, end) UTC instants."""
    first, last = _parse_day(start, "start"), _parse_day(end, "end")
    if last < first:
        raise HTTPException(400, "The end date is before the start date.")
    if (last - first).days + 1 > max_days:
        raise HTTPException(400, f"Choose a period of at most {max_days} days.")
    return reports.local_midnight_utc(first), reports.local_midnight_utc(last + timedelta(days=1)), first, last


async def _reference(request: Request) -> tuple[list, dict]:
    reader = request.app.state.cassandra_reader
    return await asyncio.gather(
        asyncio.to_thread(reader.device_metadata_sync),
        asyncio.to_thread(reader.device_thresholds_sync),
    )


def _find(metadata: list, device_id: str) -> dict:
    for meta in metadata:
        if meta["device_id"] == device_id:
            return meta
    raise HTTPException(404, "Unknown location.")


async def _hourly(request: Request, device_ids: list, start: datetime, end: datetime) -> dict:
    reader = request.app.state.cassandra_reader
    results = await asyncio.gather(
        *(asyncio.to_thread(reader.hourly_between_sync, d, start, end) for d in device_ids)
    )
    return dict(zip(device_ids, results))


async def _monthly(request: Request, month: str | None) -> dict:
    year, mon = _parse_month(month)
    metadata, thresholds = await _reference(request)
    # The year-ago month and the previous..current months, as two contiguous reads.
    ya_start, ya_end = reports.month_bounds(*reports.shift_month(year, mon, -12))
    prev_start, _ = reports.month_bounds(*reports.shift_month(year, mon, -1))
    _, cur_end = reports.month_bounds(year, mon)
    ids = [m["device_id"] for m in metadata]
    year_ago, recent = await asyncio.gather(
        _hourly(request, ids, ya_start, ya_end), _hourly(request, ids, prev_start, cur_end)
    )
    rows = {d: year_ago[d] + recent[d] for d in ids}
    report = await asyncio.to_thread(reports.monthly_report, year, mon, rows, metadata, thresholds)
    history_start = await asyncio.to_thread(request.app.state.cassandra_reader.history_start_sync)
    report["available_from"] = reports.to_local(history_start).strftime("%Y-%m") if history_start else None
    return report


@router.get("/monthly")
async def monthly(request: Request, month: str | None = None):
    return await _monthly(request, month)


@router.get("/monthly.xlsx")
async def monthly_xlsx(request: Request, month: str | None = None):
    report = await _monthly(request, month)
    body = await asyncio.to_thread(monthly_workbook, report)
    return Response(body, media_type=_XLSX, headers={
        "Content-Disposition": f'attachment; filename="environment-report-{report["month"]}.xlsx"',
    })


@router.get("/inquiry")
async def inquiry(request: Request, device_id: str, start: str, end: str, hour_from: int = 22, hour_to: int = 6):
    if not (0 <= hour_from <= 23 and 0 <= hour_to <= 23):
        raise HTTPException(400, "Hours must be between 0 and 23.")
    period_start, period_end, _, _ = _local_period(start, end, reports.MAX_INQUIRY_DAYS)
    metadata, thresholds = await _reference(request)
    meta = _find(metadata, device_id)
    heatmap_start = period_end - timedelta(days=366)
    rows = (await _hourly(request, [device_id], min(heatmap_start, period_start), period_end))[device_id]
    return await asyncio.to_thread(
        reports.inquiry_report, meta, thresholds.get(device_id, {}),
        rows, [r for r in rows if r["window_start"] >= reports.iso_utc(heatmap_start)],
        period_start, period_end, hour_from, hour_to,
    )


@router.get("/factsheet/{device_id}")
async def factsheet(request: Request, device_id: str):
    metadata, thresholds = await _reference(request)
    meta = _find(metadata, device_id)
    now = _now()
    rows = (await _hourly(request, [device_id], now - timedelta(days=366), now + timedelta(hours=1)))[device_id]
    return await asyncio.to_thread(reports.fact_sheet, meta, thresholds.get(device_id, {}), rows, now)


@router.get("/daily-pattern/{device_id}")
async def daily_pattern(request: Request, device_id: str, metric: str = "co"):
    """The month x hour heatmap alone (FR-O7), for the planner's chart area."""
    if metric not in reports.METRICS:
        raise HTTPException(400, "Unknown metric.")
    now = _now()
    rows = (await _hourly(request, [device_id], now - timedelta(days=366), now + timedelta(hours=1)))[device_id]
    result = await asyncio.to_thread(reports.heatmap, rows, metric, now)
    return {**result, "unit": environment.METRIC_UNITS[metric], "label": reports.METRIC_LABELS[metric]}


@router.get("/extract.xlsx")
async def extract_xlsx(request: Request, start: str, end: str, device_id: str = "all", metrics: str = "co,lpg,smoke,temp,humidity"):
    chosen = [m for m in metrics.split(",") if m in reports.METRICS]
    if not chosen:
        raise HTTPException(400, "Choose at least one metric.")
    period_start, period_end, first, last = _local_period(start, end, reports.MAX_EXTRACT_DAYS)
    metadata, thresholds = await _reference(request)
    locations = metadata if device_id == "all" else [_find(metadata, device_id)]
    rows = await _hourly(request, [m["device_id"] for m in locations], period_start, period_end)
    body = await asyncio.to_thread(
        extract_workbook, locations, rows, thresholds, chosen,
        first.isoformat(), (last + timedelta(days=1)).isoformat(),
    )
    name = "all-locations" if device_id == "all" else locations[0]["name"].lower()
    return Response(body, media_type=_XLSX, headers={
        "Content-Disposition": f'attachment; filename="data-extract-{name}-{first}-{last}.xlsx"',
    })
