# backend/src/schemas/alert.py
"""
Alert-level enums and structured AI diagnosis / alert payload models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AlertLevel(str, Enum):
    """Alert severity level."""

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AIDiagnosis(BaseModel):
    """Structured response from the DeepSeek AI engine."""

    error_type: str = Field(..., description="Type of error: Oops/Panic/Segfault/...")
    root_cause: str = Field(default="", description="AI-inferred root cause summary")
    ai_suggestion: str = Field(default="", description="CoT reasoning / fix steps")
    code_patch: Optional[str] = Field(default=None, description="Raw unified diff patch content, or None")
    model_used: str = Field(default="deepseek-chat")
    tokens_used: int = Field(default=0)


class AlertPayload(BaseModel):
    """WebSocket payload emitted when an alert is triggered."""

    type: str = Field(default="alert", literal=True)
    id: str = Field(default_factory=lambda: f"alert-{datetime.utcnow().timestamp()}")
    device: str
    level: AlertLevel
    summary: str = Field(..., description="Short human-readable alert summary")
    ai_suggestion: str = Field(default="")
    patch_content: Optional[str] = Field(default=None)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
