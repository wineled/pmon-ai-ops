# backend/src/schemas/log.py
"""
Structured data models for log entries and metrics extracted from raw logs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """A single parsed line from a device log file."""

    raw: str = Field(..., description="Original unprocessed line")
    timestamp: datetime | None = Field(default=None, description="Parsed timestamp if present")
    device: str = Field(default="unknown", description="Device identifier extracted from filename or line")
    level: str = Field(default="INFO", description="Log level: DEBUG/INFO/WARNING/ERROR/CRITICAL")
    message: str = Field(..., description="Log message body")
    line_number: int = Field(default=0, description="Line number in source file")


class MetricsData(BaseModel):
    """Real-time power/temperature metrics from a device log entry."""

    device: str = Field(default="unknown")
    voltage_mv: float | None = Field(default=None, ge=0, description="Voltage in millivolts")
    current_ma: float | None = Field(default=None, ge=0, description="Current in milliamps")
    temp_c: float | None = Field(default=None, description="Temperature in Celsius")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorContext(BaseModel):
    """Bundled context for an error detected in a log file."""

    device: str = Field(default="unknown")
    error_type: str = Field(..., description="Oops/Panic/Segfault/...")
    first_line: str = Field(..., description="The first line that triggered detection")
    stack_trace: str = Field(default="", description="Collected stack trace lines")
    register_dump: str = Field(default="", description="Collected register dump lines")
    surrounding_lines: list[str] = Field(default_factory=list, description="5 lines before + 5 after")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    file_path: str | None = Field(default=None)
