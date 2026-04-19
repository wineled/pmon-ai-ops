# backend/src/schemas/disasm.py
"""
Data models for binary analysis, disassembly, and address resolution.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ArchEnum(str, Enum):
    """Supported CPU architectures."""
    AUTO = "auto"
    ARM = "arm"
    ARM64 = "arm64"
    RISCV = "riscv"
    X86 = "x86"
    X86_64 = "x86_64"


class BinFileMeta(BaseModel):
    """Metadata about an uploaded binary file."""
    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    arch: str = Field(default="unknown", description="Detected/specified architecture")
    bits: int = Field(default=32, description="32 or 64 bit")
    entry_point: Optional[int] = Field(default=None, description="Entry point address")
    is_elf: bool = Field(default=False, description="Whether the file is an ELF binary")
    section_count: int = Field(default=0, description="Number of ELF sections")
    symbol_count: int = Field(default=0, description="Number of symbols found")
    disasm_lines: int = Field(default=0, description="Total disassembled instruction count")
    upload_time: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class DisasmLine(BaseModel):
    """A single disassembled instruction."""
    address: int = Field(..., description="Virtual address")
    bytes_hex: str = Field(default="", description="Hex representation of raw bytes")
    mnemonic: str = Field(default="", description="Instruction mnemonic")
    op_str: str = Field(default="", description="Operand string")
    function: str = Field(default="", description="Containing function name (if known)")
    offset_in_func: int = Field(default=0, description="Byte offset within containing function")
    is_error_addr: bool = Field(default=False, description="Whether this address appeared in an error log")


class SymbolEntry(BaseModel):
    """A symbol from the binary's symbol table."""
    name: str = Field(..., description="Symbol name")
    address: int = Field(..., description="Symbol value / address")
    size: int = Field(default=0, description="Symbol size in bytes")
    sym_type: str = Field(default="unknown", description="Symbol type: func/object/section/...")
    section: str = Field(default="", description="Containing section name")


class AddressResolveResult(BaseModel):
    """Result of resolving a memory address to source location."""
    address: int = Field(..., description="Queried address")
    function: str = Field(default="???", description="Function containing this address")
    offset: int = Field(default=0, description="Offset from function start")
    source_file: str = Field(default="", description="Source file (from addr2line if available)")
    source_line: int = Field(default=0, description="Source line number")
    instruction: str = Field(default="", description="Disassembled instruction at this address")
    nearby: list[DisasmLine] = Field(default_factory=list, description="Nearby instructions for context")


class LogAnomaly(BaseModel):
    """A code anomaly detected by correlating logs with disassembly."""
    severity: str = Field(default="WARNING", description="CRITICAL/WARNING/INFO")
    address: int = Field(..., description="Related code address")
    function: str = Field(default="???", description="Function name")
    description: str = Field(..., description="Human-readable description of the anomaly")
    log_line: str = Field(default="", description="Original log line that triggered detection")
    resolved: AddressResolveResult = Field(default_factory=lambda: AddressResolveResult(address=0))


class UploadResponse(BaseModel):
    """Response after uploading a binary file."""
    status: str = Field(default="ok")
    meta: BinFileMeta = Field(...)


class DisasmPageResponse(BaseModel):
    """Paginated disassembly response."""
    total: int = Field(..., description="Total disassembled lines")
    offset: int = Field(default=0)
    limit: int = Field(default=500)
    lines: list[DisasmLine] = Field(default_factory=list)


class SymbolPageResponse(BaseModel):
    """Paginated symbol list response."""
    total: int = Field(..., description="Total symbols")
    offset: int = Field(default=0)
    limit: int = Field(default=100)
    symbols: list[SymbolEntry] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    """Request body for log-correlated analysis."""
    log_entries: list[str] = Field(..., description="Raw log lines to analyze")
    device: str = Field(default="unknown")


class AnalysisResponse(BaseModel):
    """Response from log-correlated analysis."""
    anomalies: list[LogAnomaly] = Field(default_factory=list)
    resolved_addresses: list[AddressResolveResult] = Field(default_factory=list)
