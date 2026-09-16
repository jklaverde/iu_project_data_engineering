import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from .. import archive

logger = logging.getLogger(__name__)

# Split into two routers (not one) so main.py can gate them differently:
# Grafana's webhook has no session cookie to send, so that route must stay
# unauthenticated (reachable only on the internal Docker network in
# practice); GET /alerts is admin-role-gated like the rest of the admin UI's
# data. Matches this codebase's existing pattern of wiring auth dependencies
# at app.include_router() in main.py, not inside router modules.
webhook_router = APIRouter(prefix="/api/admin", tags=["admin"])
alerts_router = APIRouter(prefix="/api/admin", tags=["admin"])


@webhook_router.post("/alerts/webhook")
async def alerts_webhook(request: Request):
    """Receives Grafana's alertmanager-compatible webhook payload (see
    infra/grafana/provisioning/alerting/contactpoints.yaml) - one POST per
    evaluation cycle, containing a batch of alerts each with its own
    firing/resolved status."""
    payload = await request.json()
    store = request.app.state.alert_store
    received_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    for raw_alert in payload.get("alerts", []):
        labels = raw_alert.get("labels", {})
        annotations = raw_alert.get("annotations", {})
        alert = {
            "id": f"{labels.get('alertname', 'alert')}-{raw_alert.get('startsAt', received_at)}",
            "status": raw_alert.get("status", "firing"),
            "alertname": labels.get("alertname", "unknown"),
            "severity": labels.get("severity", "warning"),
            "service": labels.get("service") or labels.get("container") or labels.get("job"),
            "summary": annotations.get("summary", ""),
            "starts_at": raw_alert.get("startsAt"),
            "ends_at": raw_alert.get("endsAt"),
            "generator_url": raw_alert.get("generatorURL"),
            "received_at": received_at,
        }
        store.add(alert)
        logger.info(json.dumps({
            "event": "alert_received", "alertname": alert["alertname"], "status": alert["status"],
        }))

    # Broadcast over the existing pipeline-state WebSocket channel so any
    # connected client learns about new alerts immediately; the admin UI's
    # Alerts tab currently reads via polling (GET /alerts) for simplicity,
    # but this makes the data available for a future live-push upgrade
    # without a backend change.
    ws_manager = request.app.state.ws_manager
    await ws_manager.broadcast({"type": "alert", "data": store.recent(50)})

    return {"status": "ok"}


@alerts_router.get("/alerts")
async def alerts(request: Request):
    store = request.app.state.alert_store
    return {"alerts": store.recent(50)}


@alerts_router.post("/archive")
async def archive_and_trim(request: Request):
    """Archive-and-trim (D40, FR-A1-A3) - the sole write/mutate action
    reachable in Phase 1, admin-role-gated same as GET /alerts (main.py's
    require_admin dependency on alerts_router). confirm=true is required in
    the body since this is irreversible against the live store (FR-A3); the
    frontend's own confirmation dialog is the primary guard, this is the
    backend's independent check against a direct API call."""
    body = await request.json() if await request.body() else {}
    if not body.get("confirm"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirm=true is required to run this action")

    cutoff = None
    if body.get("cutoff"):
        cutoff = datetime.fromisoformat(body["cutoff"].replace("Z", "+00:00")).astimezone(timezone.utc)

    reader = request.app.state.cassandra_reader
    result = await asyncio.to_thread(archive.run_archive, reader, request.app.state.config.archive_dir, cutoff)
    return result
