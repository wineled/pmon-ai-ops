"""
In-memory store for recent logs and alerts.
Used by HTTP API routes when WebSocket data is not available.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..config import settings


@dataclass
class LogEntry:
    id: str
    timestamp: str
    device: str
    message: str


@dataclass
class AlertEntry:
    id: str
    device: str
    level: str
    summary: str
    ai_suggestion: str
    patch_content: str | None
    timestamp: str


class MemoryService:
    """Thread-safe in-memory store for logs and alerts."""

    def __init__(
        self,
        max_logs: int | None = None,
        max_alerts: int | None = None,
    ) -> None:
        self._logs: list[LogEntry] = []
        self._alerts: list[AlertEntry] = []
        # Use settings from config.py, fallback to defaults
        self._max_logs = max_logs or settings.memory_max_logs
        self._max_alerts = max_alerts or settings.memory_max_alerts
        self._lock = asyncio.Lock()

    # ── Logs ─────────────────────────────────────────────────────────────────

    def add_log(self, entry: dict[str, Any]) -> None:
        self._logs.append(
            LogEntry(
                id=entry.get("id", ""),
                timestamp=entry.get("timestamp", ""),
                device=entry.get("device", ""),
                message=entry.get("message", ""),
            )
        )
        if len(self._logs) > self._max_logs:
            self._logs.pop(0)

    def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {"id": e.id, "timestamp": e.timestamp, "device": e.device, "message": e.message}
            for e in self._logs[-limit:]
        ]

    # ── Alerts ───────────────────────────────────────────────────────────────

    def add_alert(self, entry: dict[str, Any]) -> None:
        self._alerts.insert(
            0,
            AlertEntry(
                id=entry.get("id", ""),
                device=entry.get("device", ""),
                level=entry.get("level", "INFO"),
                summary=entry.get("summary", ""),
                ai_suggestion=entry.get("ai_suggestion", ""),
                patch_content=entry.get("patch_content"),
                timestamp=entry.get("timestamp", ""),
            ),
        )
        if len(self._alerts) > self._max_alerts:
            self._alerts.pop()

    def get_alerts(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "id": e.id,
                "device": e.device,
                "level": e.level,
                "summary": e.summary,
                "ai_suggestion": e.ai_suggestion,
                "patch_content": e.patch_content,
                "timestamp": e.timestamp,
            }
            for e in self._alerts[:limit]
        ]

    # ── Clear ─────────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._logs.clear()
        self._alerts.clear()


# Singleton shared across the app
memory_service = MemoryService()
