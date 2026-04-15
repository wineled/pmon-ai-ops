# backend/src/api/websocket.py
"""WebSocket endpoint handler — accesses ConnectionManager via websocket.app.state."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..utils.logger import logger

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Primary WebSocket endpoint.
    Clients connect here to receive StreamPayload / MetricsPayload / AlertPayload
    broadcasts pushed from the pipeline.
    """
    # Resolve ConnectionManager from shared app state (set during lifespan startup)
    ws_manager = websocket.app.state.ws_manager

    await ws_manager.connect(websocket)
    logger.info(f"[WS] Client connected (total={ws_manager.active_count})")
    try:
        while True:
            # Keep the connection alive; recv() raises on disconnect
            data = await websocket.receive_text()
            logger.debug(f"[WS] Received from client: {data[:80]}")
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
        logger.info(f"[WS] Client disconnected (total={ws_manager.active_count})")
    except Exception as exc:
        await ws_manager.disconnect(websocket)
        logger.error(f"[WS] Unexpected error: {exc}")
