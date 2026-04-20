"""
LLM Log Analysis Service
输入: 日志文本 (10行左右)
处理: 解析异常 → 代码检索 → LLM分析定位 → 生成解决方案
输出: 结构化的分析报告
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import httpx

from ..config import settings
from ..core.ai_engine.cot_parser import parse_ai_response
from ..core.ai_engine.prompt_builder import build_log_analysis_prompt
from ..schemas.alert import AIDiagnosis
from ..utils.logger import logger

# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LogParseResult:
    raw_logs: list[str]
    error_count: int
    warning_count: int
    device: str
    error_type: str
    crash_addresses: list[int]
    crash_locations: list[str]
    severity: str
    summary: str
    raw_text: str


@dataclass
class LLMAnalysisRequest:
    logs: str | list[str]
    language: str = "auto"
    max_context_tokens: int = 8192
    code_paths: list[str] | None = None
    include_code: bool = True
    model: str | None = None


@dataclass
class LLMAnalysisResult:
    parse: LogParseResult
    diagnosis: AIDiagnosis
    success: bool
    retrieved_chunks: list = field(default_factory=list)
    code_context_used: str = ""
    processing_time_ms: int = 0
    llm_model: str = ""
    error_message: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Token Counter
# ─────────────────────────────────────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars/token."""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    alnum = len(re.findall(r"[a-zA-Z0-9_ \t.,;:\-+=]", text))
    other = len(text) - cjk - alnum
    return (alnum + cjk * 2 + other * 2) // 4


# ─────────────────────────────────────────────────────────────────────────────
# Log Parser
# ─────────────────────────────────────────────────────────────────────────────

class LogParser:
    CRITICAL_KW = {
        "fault", "crash", "panic", "abort", "hardfault", "usagefault",
        "busfault", "memfault", "assert", "trap", "die", "fatal",
        "oom", "out of memory", "nmi", "reset", "watchdog",
    }
    WARNING_KW = {
        "warn", "error", "fail", "timeout", "retry", "disconnect",
        "overflow", "underflow", "corrupt", "invalid", "denied",
        "unavailable", "unexpected",
    }

    def parse(self, logs: str | list[str]) -> LogParseResult:
        if isinstance(logs, str):
            lines = [ln.strip() for ln in logs.strip().splitlines() if ln.strip()]
        else:
            lines = [ln.strip() for ln in logs if ln.strip()]

        raw_text = "\n".join(lines)

        crit_cnt = sum(1 for ln in lines if any(k in ln.lower() for k in self.CRITICAL_KW))
        warn_cnt = sum(1 for ln in lines if any(k in ln.lower() for k in self.WARNING_KW))
        severity = "CRITICAL" if crit_cnt > 0 else "WARNING" if warn_cnt > 0 else "INFO"

        et_pat = re.compile(
            r"\b(hardfault|usagefault|busfault|memfault|assert|panic|crash|abort|fatal|oom|timeout|segfault|nullptr|overflow|watchdog|deadlock)\b",
            re.IGNORECASE
        )
        et_m = et_pat.search(raw_text)
        error_type = et_m.group(1).lower() if et_m else "unknown"

        addrs = []
        locs = []
        for pat, lbl in [
            (re.compile(r"(?:PC|pc).*?(?:0x)([0-9a-fA-F]{8})"), "PC"),
            (re.compile(r"(?:LR|link).*?(?:0x)([0-9a-fA-F]{8})"), "LR"),
            (re.compile(r"RIP.*?(?:0x)?([0-9a-fA-F]{8})", re.IGNORECASE), "RIP"),
        ]:
            for m in pat.finditer(raw_text):
                try:
                    a = int(m.group(1), 16)
                    addrs.append(a)
                    locs.append(f"{lbl}=0x{a:08X}")
                except ValueError:
                    pass

        dev_m = re.search(r"(PMON|pmon|STM32|NXP|Cortex|ARM|PowerPC)", raw_text)
        device = dev_m.group(1) if dev_m else "unknown"

        summary = self._summarize(lines, severity, error_type)

        return LogParseResult(
            raw_logs=lines,
            error_count=crit_cnt + warn_cnt,
            warning_count=warn_cnt,
            device=device,
            error_type=error_type,
            crash_addresses=addrs,
            crash_locations=locs,
            severity=severity,
            summary=summary,
            raw_text=raw_text,
        )

    def _summarize(self, lines: list[str], severity: str, etype: str) -> str:
        for line in lines:
            low = line.lower()
            if any(k in low for k in self.CRITICAL_KW):
                return (line[:120] + "...") if len(line) > 120 else line
        for line in lines:
            if line.strip() and len(line.strip()) > 10:
                return (line[:120] + "...") if len(line) > 120 else line
        return f"[{severity}] {etype} ({len(lines)} lines)"


# ─────────────────────────────────────────────────────────────────────────────
# LLM Service
# ─────────────────────────────────────────────────────────────────────────────

class LLMAnalysisService:
    def __init__(self):
        self.parser = LogParser()

    async def analyze(self, req: LLMAnalysisRequest) -> LLMAnalysisResult:
        t0 = time.time()
        model = req.model or settings.deepseek_model

        try:
            parse_result = self.parser.parse(req.logs)
        except Exception as e:
            logger.warning(f"[LLMLog] Parse error: {e}")
            parse_result = self.parser.parse(["parse error", str(e)])

        retrieved = []
        code_context = ""
        if req.include_code:
            try:
                from .code_index_service import get_code_index
                index = get_code_index()
                if index.stats and index.stats.total_chunks > 0:
                    query = self._build_query(parse_result)
                    retrieved = index.retrieve(
                        query=query, top_k=10,
                        max_tokens=req.max_context_tokens,
                    )
                    code_context = index.get_context_for_llm(
                        query=query, max_tokens=req.max_context_tokens,
                    )
                    logger.info(f"[LLMLog] Retrieved {len(retrieved)} chunks")
                else:
                    logger.warning("[LLMLog] Code index not built")
                    code_context = self._fallback_ctx(parse_result)
            except Exception as e:
                logger.warning(f"[LLMLog] Retrieval error: {e}")
                code_context = self._fallback_ctx(parse_result)
        else:
            code_context = "/* No code context */"

        try:
            diagnosis = await self._call_llm(parse_result, code_context, model, req.language)
        except Exception as e:
            logger.error(f"[LLMLog] LLM error: {e}")
            diagnosis = AIDiagnosis(
                error_type=parse_result.error_type,
                root_cause=f"[LLM unavailable] {e}",
                ai_suggestion=(
                    "Check: 1) DeepSeek API key configured, "
                    "2) API endpoint reachable, 3) Code index built (/api/llm/index)"
                ),
            )

        elapsed_ms = int((time.time() - t0) * 1000)
        return LLMAnalysisResult(
            parse=parse_result,
            retrieved_chunks=retrieved,
            diagnosis=diagnosis,
            code_context_used=code_context[:2000],
            processing_time_ms=elapsed_ms,
            llm_model=model,
            success=(diagnosis.ai_suggestion != diagnosis.root_cause),
        )

    async def _call_llm(self, parse_result, code_context, model, language):
        sys_p, user_p = build_log_analysis_prompt(parse_result, code_context, language)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": user_p},
            ],
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        async with httpx.AsyncClient(
            base_url=settings.deepseek_base_url,
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            timeout=httpx.Timeout(60.0),
        ) as client:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        diagnosis = parse_ai_response(raw, parse_result.error_type)
        logger.info(f"[LLMLog] Done in {data.get('usage', {}).get('total_tokens', '?')} tokens")
        return diagnosis

    def _build_query(self, p: LogParseResult) -> str:
        parts = [p.error_type, p.device]
        for a in p.crash_addresses[:3]:
            parts.append(f"0x{a:08X}")
        parts.extend(p.crash_locations[:5])
        if p.summary:
            parts.append(p.summary[:200])
        return " ".join(parts)

    def _fallback_ctx(self, p: LogParseResult) -> str:
        addrs = ", ".join(f"0x{a:08X}" for a in p.crash_addresses[:3])
        return f"/* Code index not available */\n/* Device: {p.device} | Type: {p.error_type} | Addrs: {addrs} */"


_llm_svc: LLMAnalysisService | None = None


def get_llm_service() -> LLMAnalysisService:
    global _llm_svc
    if _llm_svc is None:
        _llm_svc = LLMAnalysisService()
    return _llm_svc
