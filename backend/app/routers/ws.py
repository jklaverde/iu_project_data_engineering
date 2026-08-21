import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth import COOKIE_NAME, verify_session_token

router = APIRouter(tags=["ws"])


@router.websocket("/ws/pipeline-state")
async def ws_pipeline_state(websocket: WebSocket):
    config = websocket.app.state.config
    token = websocket.cookies.get(COOKIE_NAME)
    if token is None or verify_session_token(token, config) is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    ws_manager = websocket.app.state.ws_manager
    await ws_manager.connect(websocket)

    try:
        snapshot = await websocket.app.state.poller.get_snapshot()
        await websocket.send_json({"type": "pipeline-state", "data": snapshot})
        while True:
            # No client->server messages expected; this just keeps the
            # connection open and detects disconnects. Broadcasts arrive via
            # ws_manager.broadcast() from the state poller loops.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        await ws_manager.disconnect(websocket)
