# backend/src/core/notifier/manager.py
"""
Thread-safe WebSocket connection pool.
Allows concurrent connect/disconnect and broadcast operations.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import WebSocket

from ...schemas.ws_message import WSPayload
from ...utils.logger import logger

if TYPE_CHECKING:
    pass


class ConnectionManager:
    """
    Manages active WebSocket connections for the /ws endpoint.

    Operations are guarded by an asyncio.Lock to ensure thread safety.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Connection lifecycle ─────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket client."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(f"[WS] Client connected (total={len(self._connections)})")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket client."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(f"[WS] Client disconnected (total={len(self._connections)})")

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast(self, payload: WSPayload) -> None:
        """
        Serialise *payload* and send it to every connected client.

        Silently skips clients that have already closed the connection.
        """
        import json

        import orjson

        # orjson is ~2× faster than stdlib json
        try:
            data = orjson.dumps(payload.model_dump(mode="json"))
        except ImportError:
            import json

            data = json.dumps(payload.model_dump()).encode()

        async with self._lock:
            dead: set[WebSocket] = set()
            for ws in self._connections:
                try:
                    await ws.send_bytes(data)
                except Exception:
                    dead.add(ws)

            # Clean up broken connections
            for ws in dead:
                self._connections.discard(ws)

    @property
    def active_count(self) -> int:
        """Return the number of currently connected clients (approximate)."""
        return len(self._connections)
