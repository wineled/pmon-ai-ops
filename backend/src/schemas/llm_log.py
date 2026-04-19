"""
LLM Log Analysis API schemas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Language(str, Enum):
    """Response language."""
    AUTO = "auto"
    ZH = "zh"
    EN = "en"


class Severity(str, Enum):
    """Inferred log severity."""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response
# ─────────────────────────────────────────────────────────────────────────────

class LLMLogRequest(BaseModel):
    """Request for LLM-powered log analysis."""

    logs: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Log lines (1-100 lines). "
            "Can be raw TFTP stream text split by newline.",
    )

    language: Language = Field(
        default=Language.AUTO,
        description="Response language: auto / zh / en",
    )

    include_code: bool = Field(
        default=True,
        description="Whether to retrieve local source code as context",
    )

    max_context_tokens: int = Field(
        default=8192,
        ge=512,
        le=32768,
        description="Token budget for retrieved code context",
    )

    model: Optional[str] = Field(
        default=None,
        description="Override default LLM model",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "logs": [
                    "[PMON] System started OK",
                    "PC is at 0x08000104",
                    "LR is at 0x08000208",
                    "HardFault: CFSR=0x82000000 HFSR=0x40000000",
                    "[PMON] Assertion failed: buffer != NULL",
                ],
                "language": "zh",
                "include_code": True,
            }
        }


class CrashAddress(BaseModel):
    """Extracted crash address."""
    address: int = Field(..., description="Integer address value")
    hex: str = Field(..., description="Hex string e.g. 0x08000104")
    label: str = Field(default="", description="Label e.g. PC, LR, RIP")


class LogParseResult(BaseModel):
    """Result of log parsing (without LLM)."""
    error_count: int
    warning_count: int
    device: str
    error_type: str
    severity: Severity
    crash_addresses: list[CrashAddress]
    summary: str
    raw_text: str


class RetrievedChunk(BaseModel):
    """A retrieved code chunk."""
    chunk_id: str
    file_path: str
    line_start: int
    line_end: int
    function_name: str = ""
    language: str = ""
    content_preview: str = Field(..., description="First 200 chars")
    score: float
    relevance: str = Field(
        default="related",
        description="core | related | peripheral",
    )


class LLMLogResponse(BaseModel):
    """Response from LLM log analysis."""
    success: bool
    parse: LogParseResult
    diagnosis: dict  # AIDiagnosis as dict
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    code_context_preview: str = Field(
        default="",
        description="First 500 chars of code context used",
    )
    processing_time_ms: int
    llm_model: str
    error_message: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Index management
# ─────────────────────────────────────────────────────────────────────────────

class IndexStats(BaseModel):
    """Code index statistics."""
    total_files: int
    total_chunks: int
    total_lines: int
    total_size_mb: float
    languages: dict[str, int]
    indexed_at: str


class IndexRequest(BaseModel):
    """Request to build/rebuild the code index."""
    code_paths: list[str] = Field(
        default_factory=list,
        description="Directories/files to index. "
            "Defaults to project root.",
    )
    force_rebuild: bool = Field(
        default=False,
        description="Force rebuild even if already built",
    )


class IndexResponse(BaseModel):
    """Response from index build."""
    success: bool
    stats: IndexStats | None = None
    error: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Batch / streaming
# ─────────────────────────────────────────────────────────────────────────────

class BatchLLMLogRequest(BaseModel):
    """Batch log analysis request."""
    logs_list: list[list[str]] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Up to 20 log sets to analyze",
    )
    language: Language = Field(default=Language.AUTO)
    include_code: bool = Field(default=True)


class BatchLLMLogResponse(BaseModel):
    """Batch analysis results."""
    results: list[LLMLogResponse]
    total_time_ms: int
    success_count: int
    failure_count: int
