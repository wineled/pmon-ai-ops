"""
LLM Log Analysis API Router
POST /api/llm/log        - Analyze logs with LLM + code retrieval
POST /api/llm/index       - Build code index
GET  /api/llm/index/status - Check index status
GET  /api/llm/retrieve   - Search code (standalone)
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from ..config import settings
from ..schemas.llm_log import (
    BatchLLMLogRequest,
    BatchLLMLogResponse,
    CrashAddress,
    IndexRequest,
    IndexResponse,
    IndexStats,
    LLMLogRequest,
    LLMLogResponse,
    LogParseResult,
    RetrievedChunk,
    Severity,
)
from ..services.code_index_service import (
    build_code_index,
    get_code_index,
)
from ..services.llm_analysis_service import (
    get_llm_service,
)
from ..utils.logger import logger

llm_router = APIRouter(prefix="/api/llm", tags=["llm"])


# ─────────────────────────────────────────────────────────────────────────────
# Log Analysis
# ─────────────────────────────────────────────────────────────────────────────

@llm_router.post("/log", response_model=LLMLogResponse)
async def analyze_logs(req: LLMLogRequest) -> LLMLogResponse:
    """
    Analyze logs with LLM + automatic code retrieval.

    Pipeline:
    1. Parse log → structured info (addresses, error type, severity)
    2. Retrieve relevant code from local source (RAG)
    3. Call DeepSeek LLM with context
    4. Return structured diagnosis + code references
    """
    service = get_llm_service()

    try:
        result = await service.analyze(
            req=req,
        )
    except Exception as e:
        logger.error(f"[LLM Router] analyze error: {e}")
        # Return parse-only result on LLM failure
        parser = service.parser
        parse_result = parser.parse(req.logs)
        return LLMLogResponse(
            success=False,
            parse=_to_parse_result(parse_result),
            diagnosis={},
            retrieved_chunks=[],
            processing_time_ms=0,
            llm_model=req.model or "deepseek-chat",
            error_message=str(e),
        )

    # Build response
    retrieved = [
        RetrievedChunk(
            chunk_id=c.chunk.chunk_id,
            file_path=c.chunk.file_path,
            line_start=c.chunk.line_start,
            line_end=c.chunk.line_end,
            function_name=c.chunk.function_name,
            language=c.chunk.language,
            content_preview=c.chunk.content[:200],
            score=c.score,
            relevance=c.relevance_label,
        )
        for c in result.retrieved_chunks
    ]

    return LLMLogResponse(
        success=result.success,
        parse=_to_parse_result(result.parse),
        diagnosis={
            "error_type": result.diagnosis.error_type,
            "root_cause": result.diagnosis.root_cause,
            "ai_suggestion": result.diagnosis.ai_suggestion,
            "code_patch": result.diagnosis.code_patch,
        },
        retrieved_chunks=retrieved,
        code_context_preview=result.code_context_used[:500],
        processing_time_ms=result.processing_time_ms,
        llm_model=result.llm_model,
        error_message=result.diagnosis.ai_suggestion
            if not result.success else "",
    )


@llm_router.post("/log/batch", response_model=BatchLLMLogResponse)
async def batch_analyze(reqs: BatchLLMLogRequest) -> BatchLLMLogResponse:
    """
    Analyze multiple log sets in parallel.
    Up to 20 log sets, each processed concurrently.
    """
    import time
    t0 = time.time()

    async def analyze_one(logs: list[str]) -> LLMLogResponse:
        req = LLMLogRequest(
            logs=logs,
            language=reqs.language,
            include_code=reqs.include_code,
        )
        return await analyze_logs(req)

    results = await asyncio.gather(
        *[analyze_one(logs) for logs in reqs.logs_list],
        return_exceptions=True,
    )

    responses = []
    success_count = 0
    for r in results:
        if isinstance(r, Exception):
            responses.append(LLMLogResponse(
                success=False,
                parse=LogParseResult(
                    error_count=0, warning_count=0, device="unknown",
                    error_type="unknown", severity=Severity.INFO,
                    crash_addresses=[], summary="", raw_text="",
                ),
                diagnosis={},
                processing_time_ms=0,
                llm_model="",
                error_message=str(r),
            ))
        else:
            responses.append(r)
            if r.success:
                success_count += 1

    total_ms = int((time.time() - t0) * 1000)

    return BatchLLMLogResponse(
        results=responses,
        total_time_ms=total_ms,
        success_count=success_count,
        failure_count=len(responses) - success_count,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Code Index Management
# ─────────────────────────────────────────────────────────────────────────────

@llm_router.post("/index", response_model=IndexResponse)
async def build_index(req: IndexRequest) -> IndexResponse:
    """
    Build (or rebuild) the code index for LLM context retrieval.

    Scans the project directory for source files and indexes them.
    Typically takes 5-30s for large codebases.
    """
    try:
        # Determine paths to index
        paths = req.code_paths or settings.code_index_paths

        stats = build_code_index(paths, default_dirs=settings.code_index_paths)

        return IndexResponse(success=True, stats=_to_index_stats(stats))

    except Exception as e:
        logger.error(f"[LLM Router] index build error: {e}")
        return IndexResponse(success=False, error=str(e))


@llm_router.get("/index/status", response_model=IndexResponse)
async def index_status() -> IndexResponse:
    """Get the current code index status."""
    try:
        index = get_code_index()
        if index.stats is None:
            return IndexResponse(
                success=False,
                error="Index not built yet. POST /api/llm/index to build.",
            )
        return IndexResponse(success=True, stats=_to_index_stats(index.stats))
    except Exception as e:
        return IndexResponse(success=False, error=str(e))


@llm_router.get("/retrieve")
async def retrieve_code(
    q: str = Query(..., min_length=3, description="Search query"),
    top_k: int = Query(default=10, ge=1, le=50),
    lang: str | None = Query(default=None, description="Filter by language"),
) -> dict:
    """
    Standalone code retrieval (no LLM).
    Useful for testing the RAG pipeline independently.
    """
    try:
        index = get_code_index()
        if index.stats is None or index.stats.total_chunks == 0:
            return {
                "query": q,
                "chunks": [],
                "total_indexed": 0,
                "message": "Index not built. POST /api/llm/index first.",
            }

        results = index.retrieve(q, top_k=top_k, lang_filter=lang)

        return {
            "query": q,
            "chunks": [
                {
                    "chunk_id": r.chunk.chunk_id,
                    "file_path": r.chunk.file_path,
                    "lines": f"{r.chunk.line_start}-{r.chunk.line_end}",
                    "function": r.chunk.function_name,
                    "language": r.chunk.language,
                    "score": r.score,
                    "relevance": r.relevance_label,
                    "content_preview": r.chunk.content[:300],
                }
                for r in results
            ],
            "total_indexed": index.stats.total_chunks,
        }

    except Exception as e:
        return {"query": q, "chunks": [], "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_parse_result(p) -> LogParseResult:
    """Convert LogParseResult dataclass to Pydantic model."""
    return LogParseResult(
        error_count=p.error_count,
        warning_count=p.warning_count,
        device=p.device,
        error_type=p.error_type,
        severity=Severity(p.severity),
        crash_addresses=[
            CrashAddress(address=a, hex=f"0x{a:08X}", label=loc)
            for a, loc in zip(p.crash_addresses, p.crash_locations or [], strict=False)
        ],
        summary=p.summary,
        raw_text=p.raw_text,
    )


def _to_index_stats(s) -> IndexStats:
    """Convert IndexStats dataclass to Pydantic model."""
    return IndexStats(
        total_files=s.total_files,
        total_chunks=s.total_chunks,
        total_lines=s.total_lines,
        total_size_mb=round(s.total_size_bytes / 1024 / 1024, 2),
        languages=s.languages,
        indexed_at=s.indexed_at,
    )
