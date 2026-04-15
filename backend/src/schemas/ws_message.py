# backend/src/schemas/ws_message.py
"""
Union of all WebSocket message types pushed to the frontend.
Matches the exact schema expected by the frontend WebSocket consumer.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

from .alert import AlertPayload
from .log import MetricsData


class StreamPayload(BaseModel):
    """TFTP transfer progress / stream event payload."""

    type: Literal["stream"] = "stream"
    device: str
    lines_per_sec: float = Field(ge=0.0, description="Estimated log lines per second")
    bytes_transferred: int = Field(ge=0, description="Total bytes transferred in this file")


class MetricsPayload(BaseModel):
    """Real-time hardware metrics payload."""

    type: Literal["metrics"] = "metrics"
    device: str
    voltage_mv: float
    current_ma: float
    temp_c: float


# Union alias — used by ConnectionManager.broadcast()
WSPayload = Union[StreamPayload, MetricsPayload, AlertPayload]


# ── Helper factories ───────────────────────────────────────────────────────────

def metrics_to_payload(m: MetricsData) -> MetricsPayload:
    """Convert internal MetricsData to the wire format MetricsPayload."""
    return MetricsPayload(
        device=m.device,
        voltage_mv=m.voltage_mv or 0.0,
        current_ma=m.current_ma or 0.0,
        temp_c=m.temp_c or 0.0,
    )
