# backend/src/core/notifier/dispatcher.py
"""
Format and dispatch typed WebSocket messages to the ConnectionManager.
"""

from pathlib import Path

from ...schemas.alert import AlertLevel, AlertPayload, AIDiagnosis
from ...schemas.log import MetricsData
from ...schemas.ws_message import MetricsPayload, StreamPayload, metrics_to_payload
from ...services.memory_service import memory_service
from ...utils.logger import logger
from .manager import ConnectionManager


def make_stream_payload(device: str, bytes_transferred: int) -> StreamPayload:
    """Build a StreamPayload from file transfer metadata."""
    # Rough estimate: assume average log line ~100 bytes → lines/s
    lines_per_sec = bytes_transferred / 100.0
    return StreamPayload(
        device=device,
        lines_per_sec=round(lines_per_sec, 2),
        bytes_transferred=bytes_transferred,
    )


def make_alert_payload(diagnosis: AIDiagnosis, device: str) -> AlertPayload:
    """Build an AlertPayload from a DeepSeek AIDiagnosis."""
    level_map = {
        "Kernel Panic": AlertLevel.CRITICAL,
        "Kernel Oops": AlertLevel.WARNING,
        "Segfault": AlertLevel.CRITICAL,
        "Timeout": AlertLevel.WARNING,
    }
    return AlertPayload(
        device=device,
        level=level_map.get(diagnosis.error_type, AlertLevel.INFO),
        summary=diagnosis.root_cause[:200],
        ai_suggestion=diagnosis.ai_suggestion,
        patch_content=diagnosis.code_patch,
    )


async def dispatch_metrics(ws_manager: ConnectionManager, metrics_list: list[MetricsData]) -> None:
    """Broadcast each MetricsData as a MetricsPayload."""
    for m in metrics_list:
        payload = metrics_to_payload(m)
        await ws_manager.broadcast(payload)


async def dispatch_stream(ws_manager: ConnectionManager, device: str, bytes_transferred: int) -> None:
    """Broadcast a StreamPayload."""
    await ws_manager.broadcast(make_stream_payload(device, bytes_transferred))


async def dispatch_alert(ws_manager: ConnectionManager, diagnosis: AIDiagnosis, device: str) -> None:
    """Broadcast an AlertPayload and store in memory."""
    alert = make_alert_payload(diagnosis, device)
    await ws_manager.broadcast(alert)
    memory_service.add_alert({
        "id": f"{device}-{alert.timestamp}",
        "device": device,
        "level": alert.level.value if hasattr(alert.level, "value") else alert.level,
        "summary": alert.summary,
        "ai_suggestion": alert.ai_suggestion,
        "patch_content": alert.patch_content,
        "timestamp": alert.timestamp,
    })
