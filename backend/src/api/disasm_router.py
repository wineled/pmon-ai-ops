"""
Disassembly API Router: upload, status, disassembly, symbols, resolve, analyze.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..schemas.disasm import (
    AddressResolveResult,
    AnalysisRequest,
    AnalysisResponse,
    DisasmPageResponse,
    SymbolPageResponse,
    UploadResponse,
)
from ..services.disasm_service import disasm_service
from ..utils.logger import logger

disasm_router = APIRouter(prefix="/api/disasm", tags=["disasm"])


@disasm_router.post("/upload", response_model=UploadResponse)
async def upload_binary(
    file: UploadFile = File(...),  # noqa: B008
    arch: str = Form(default="auto"),  # noqa: B008
    base_addr: str = Form(default="0x0"),
) -> UploadResponse:
    """
    Upload a binary file (ELF or raw) for disassembly analysis.

    - **file**: Binary file (.elf, .bin, .axf, etc.)
    - **arch**: Architecture hint: auto / arm / arm64 / riscv / x86 / x86_64
    - **base_addr**: Base address for raw binaries (hex string, e.g. 0x08000000)
    """
    data = await file.read()
    filename = file.filename or "unknown.bin"

    # Parse base address
    try:
        base = int(base_addr, 16) if base_addr.startswith("0x") else int(base_addr, 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base_addr: {base_addr}") from exc

    try:
        meta = disasm_service.load_binary(data, filename, arch=arch, base_addr=base)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(f"[API/disasm] Uploaded {filename}: arch={meta.arch}, symbols={meta.symbol_count}")
    return UploadResponse(status="ok", meta=meta)


@disasm_router.get("/status")
async def get_status() -> dict:
    """Return current disassembly status."""
    meta = disasm_service.get_meta()
    if meta is None:
        return {"loaded": False, "meta": None}
    return {"loaded": True, "meta": meta.model_dump()}


@disasm_router.get("/disassembly", response_model=DisasmPageResponse)
async def get_disassembly(
    offset: int = 0,
    limit: int = 500,
) -> DisasmPageResponse:
    """
    Get paginated disassembly output.

    - **offset**: Line index to start from
    - **limit**: Maximum lines to return (max 2000)
    """
    limit = min(limit, 2000)
    return disasm_service.get_disassembly(offset=offset, limit=limit)


@disasm_router.get("/symbols", response_model=SymbolPageResponse)
async def get_symbols(
    query: str = "",
    offset: int = 0,
    limit: int = 100,
) -> SymbolPageResponse:
    """
    Get symbol list, optionally filtered by name.

    - **query**: Filter symbols by name (case-insensitive substring)
    - **offset**: Symbol index to start from
    - **limit**: Maximum symbols to return
    """
    return disasm_service.get_symbols(query=query, offset=offset, limit=limit)


@disasm_router.get("/resolve", response_model=AddressResolveResult)
async def resolve_address(address: str) -> AddressResolveResult:
    """
    Resolve a memory address to its containing function and instruction.

    - **address**: Hex address string (e.g. 0x08001234)
    """
    try:
        addr = int(address, 16) if address.startswith("0x") else int(address, 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid address: {address}") from exc

    return disasm_service.resolve_address(addr)


@disasm_router.post("/analyze", response_model=AnalysisResponse)
async def analyze_logs(body: AnalysisRequest) -> AnalysisResponse:
    """
    Analyze log entries and correlate with loaded binary.

    Extracts crash addresses from log lines and resolves them
    to function names and instructions.
    """
    return disasm_service.analyze_logs(body.log_entries, device=body.device)


@disasm_router.delete("/clear")
async def clear_binary() -> dict:
    """Clear the currently loaded binary."""
    disasm_service.clear()
    return {"status": "ok", "message": "Binary cleared"}
