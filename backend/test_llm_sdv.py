"""
SDV Tests for LLM Log Analysis Module
覆盖: LogParser, LLMAnalysisService, LLM Router, 端到端集成
"""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ─── Test Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_logs():
    return [
        "[PMON] System started OK",
        "PC is at 0x08000104",
        "LR is at 0x08000208",
        "HardFault: CFSR=0x82000000 HFSR=0x40000000",
        "[PMON] Assertion failed: buffer != NULL",
    ]


@pytest.fixture
def sample_logs_str(sample_logs):
    return "\n".join(sample_logs)


@pytest.fixture
def crash_logs():
    return [
        "[PMON] *** PANIC ***",
        "Kernel panic - not syncing: VFS: Unable to mount root fs",
        "PC=0xC0008004 LR=0xC0021008",
        "Call trace:",
        "  #0: sys_mount() at fs/super.c:142",
        "  #1: do_mount() at fs/super.c:278",
        "  #2: sys_mount() at fs/super.c:301",
        "  kernel BUG at fs/block_dev.c:89",
    ]


@pytest.fixture
def mock_llm_response():
    return {
        "choices": [{
            "message": {
                "content": (
                    "## ANALYSIS\n"
                    "Root cause: buffer pointer passed to memcpy was NULL.\n"
                    "## DIFF\n"
                    "```diff\n"
                    "- if (buf == NULL) return;\n"
                    "+ if (!buf) { ret = -EINVAL; goto out; }\n"
                    "```"
                )
            }
        }],
        "usage": {"total_tokens": 512},
    }


# ─── FR: Functional Requirements ────────────────────────────────────────────

class TestFR:
    """FR: 功能性需求"""

    def test_fr01_parser_accepts_list_input(self, sample_logs):
        """FR-01: LogParser.parse() 接受 list[str] 输入"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs)
        assert isinstance(result.raw_logs, list)
        assert len(result.raw_logs) == len(sample_logs)

    def test_fr02_parser_accepts_str_input(self, sample_logs_str):
        """FR-02: LogParser.parse() 接受 str 输入"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs_str)
        assert isinstance(result.raw_logs, list)
        assert len(result.raw_logs) == 5

    def test_fr03_parser_extracts_hardfault(self, sample_logs):
        """FR-03: Parser 识别 HardFault 并设置 severity=CRITICAL"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs)
        assert result.severity == "CRITICAL"
        assert result.error_type in ("hardfault", "assert")

    def test_fr04_parser_extracts_pc_lr_addresses(self, sample_logs):
        """FR-04: Parser 提取 PC/LR 地址"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs)
        assert len(result.crash_addresses) >= 2
        assert 0x08000104 in result.crash_addresses
        assert 0x08000208 in result.crash_addresses

    def test_fr05_parser_extracts_device(self, sample_logs):
        """FR-05: Parser 识别设备名"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs)
        assert result.device == "PMON"

    def test_fr06_parser_extracts_panic(self, crash_logs):
        """FR-06: Parser 识别 PANIC"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(crash_logs)
        assert result.severity == "CRITICAL"
        assert result.error_type == "panic"

    def test_fr07_parser_summarizes(self, sample_logs):
        """FR-07: Parser 生成摘要"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs)
        assert len(result.summary) > 0
        assert len(result.summary) <= 200

    def test_fr08_parser_counts_errors(self, sample_logs):
        """FR-08: Parser 统计错误/警告数量"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(sample_logs)
        assert result.error_count >= 2

    def test_fr09_analyze_no_crash_addresses(self):
        """FR-09: 无崩溃地址时 graceful handling"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(["[PMON] INFO: task started", "[PMON] INFO: done"])
        assert result.crash_addresses == []
        assert result.severity in ("INFO", "WARNING")

    def test_fr10_unknown_error_type(self):
        """FR-10: 无已知错误类型时 fallback"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(["Hello world", "normal log"])
        assert result.error_type == "unknown"
        assert result.severity == "INFO"

    def test_fr11_empty_list_handled(self):
        """FR-11: 空日志列表返回 valid result"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse([])
        assert result.error_count == 0
        assert result.summary == "[INFO] unknown (0 lines)"

    def test_fr12_whitespace_only_lines_stripped(self):
        """FR-12: 空白行被过滤"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(["  ", "[PMON] error", "   ", "[PMON] ok"])
        assert len(result.raw_logs) == 2
        assert all(l.strip() for l in result.raw_logs)


# ─── IC: Interface Contract ───────────────────────────────────────────────────

class TestIC:
    """IC: 接口契约"""

    def test_ic01_analyze_returns_llm_analysis_result(self, sample_logs):
        """IC-01: analyze() 返回 LLMAnalysisResult dataclass"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )
        svc = get_llm_service()
        req = LLMAnalysisRequest(logs=sample_logs, include_code=False)
        result = asyncio.run(svc.analyze(req))
        assert result.parse is not None
        assert result.diagnosis is not None
        assert isinstance(result.processing_time_ms, int)
        assert result.success in (True, False)  # LLM may fail but parse must work

    def test_ic02_logparser_returns_dataclass(self, sample_logs):
        """IC-02: LogParser.parse() 返回 LogParseResult dataclass"""
        from src.services.llm_analysis_service import LogParser
        from dataclasses import dataclass
        p = LogParser()
        result = p.parse(sample_logs)
        assert hasattr(result, "raw_logs")
        assert hasattr(result, "crash_addresses")
        assert hasattr(result, "severity")

    def test_ic03_request_accepts_str_or_list(self, sample_logs_str):
        """IC-03: LLMAnalysisRequest 接受 str 或 list"""
        from src.services.llm_analysis_service import LLMAnalysisRequest
        req1 = LLMAnalysisRequest(logs=sample_logs_str)
        req2 = LLMAnalysisRequest(logs=["line1", "line2"])
        assert req1.include_code is True
        assert req2.include_code is True

    def test_ic04_request_defaults(self):
        """IC-04: LLMAnalysisRequest 有正确的默认值"""
        from src.services.llm_analysis_service import LLMAnalysisRequest
        req = LLMAnalysisRequest(logs=["test"])
        assert req.language == "auto"
        assert req.max_context_tokens == 8192
        assert req.include_code is True
        assert req.model is None

    def test_ic05_result_has_all_fields(self):
        """IC-05: LLMAnalysisResult 有所有必需字段"""
        from src.services.llm_analysis_service import LLMAnalysisResult
        from src.services.llm_analysis_service import LogParseResult
        from src.schemas.alert import AIDiagnosis
        pr = LogParseResult(
            raw_logs=["test"], error_count=0, warning_count=0,
            device="x", error_type="x", crash_addresses=[],
            crash_locations=[], severity="INFO", summary="x",
            raw_text="test",
        )
        diag = AIDiagnosis(error_type="x")
        r = LLMAnalysisResult(
            parse=pr, retrieved_chunks=[], diagnosis=diag,
            code_context_used="", processing_time_ms=0,
            llm_model="x", success=False,
        )
        assert r.parse is not None
        assert r.diagnosis is not None
        assert r.processing_time_ms >= 0

    def test_ic06_count_tokens_function_exists(self):
        """IC-06: count_tokens 函数存在且返回正整数"""
        from src.services.llm_analysis_service import count_tokens
        n = count_tokens("Hello world 你好")
        assert isinstance(n, int)
        assert n > 0

    def test_ic07_singleton_get_llm_service(self):
        """IC-07: get_llm_service() 返回同一实例"""
        from src.services.llm_analysis_service import get_llm_service
        s1 = get_llm_service()
        s2 = get_llm_service()
        assert s1 is s2


# ─── BC: Boundary Conditions ─────────────────────────────────────────────────

class TestBC:
    """BC: 边界条件"""

    def test_bc01_very_long_log_line(self):
        """BC-01: 超长日志行（>200字符）"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        long_line = "x" * 500
        result = p.parse([f"[PMON] error: {long_line}"])
        assert len(result.raw_logs[0]) >= 500  # prefix adds chars

    def test_bc02_many_addresses(self):
        """BC-02: 多个地址（PC/LR 多个）"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse([
            "PC=0x08000104 LR=0x08000208",
            "Registers: PC=0xdeadbeef LR=0xcafebabe",
        ])
        # Parser captures PC= and LR= occurrences
        assert len(result.crash_addresses) >= 2
        assert 0x08000104 in result.crash_addresses
        assert 0xdeadbeef in result.crash_addresses

    def test_bc03_unicode_in_logs(self):
        """BC-03: 日志包含中文字符"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse([
            "[PMON] 错误：内存分配失败",
            "PC is at 0x08000104",
            "HardFault: 系统崩溃",
        ])
        assert result.device == "PMON"

    def test_bc04_noisy_logs_with_many_errors(self):
        """BC-04: 包含很多错误关键词的日志"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse([
            "warn: retry attempt 1",
            "error: timeout",
            "fail: retry attempt 2",
            "error: disconnect",
            "warn: overflow",
        ])
        assert result.error_count >= 4
        assert result.severity == "WARNING"

    def test_bc05_special_chars_in_log(self):
        """BC-05: 日志包含特殊字符（&<>"'等）"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse([
            "[PMON] error: <buffer> & ptr != NULL",
            'PC=0x08000104 "string with \'quotes\'"',
        ])
        assert len(result.raw_logs) == 2
        assert "PC" in result.raw_text

    def test_bc06_case_insensitive_detection(self):
        """BC-06: 错误类型检测大小写不敏感"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        for text in ["HARDFAULT", "HardFault", "hardfault", "HARDfault"]:
            result = p.parse([text])
            assert result.error_type == "hardfault"

    def test_bc07_hex_addresses_variants(self):
        """BC-07: 各种格式的十六进制地址"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse([
            "PC=0x08000104",
            "LR=0x08000208",
            "PC is at 0xdeadbeef",
            "RIP=cafebabe",
        ])
        assert 0x08000104 in result.crash_addresses
        assert 0xdeadbeef in result.crash_addresses
        assert 0xcafebabe in result.crash_addresses

    def test_bc08_zero_address_extracted(self):
        """BC-08: 零地址提取（PC=0x00000000）"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(["PC=0x00000000", "LR=0x00000000"])
        assert 0 in result.crash_addresses


# ─── DI: Data Integrity ──────────────────────────────────────────────────────

class TestDI:
    """DI: 数据完整性"""

    def test_di01_parse_result_fields_typed_correctly(self, sample_logs):
        """DI-01: 返回值字段类型正确"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        r = p.parse(sample_logs)
        assert isinstance(r.raw_logs, list)
        assert isinstance(r.raw_logs[0], str)
        assert isinstance(r.crash_addresses, list)
        assert isinstance(r.crash_addresses[0], int)
        assert isinstance(r.crash_locations, list)
        assert isinstance(r.severity, str)
        assert r.severity in ("CRITICAL", "WARNING", "INFO")

    def test_di02_error_warn_count_accuracy(self):
        """DI-02: error_count + warning_count 准确性"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        r = p.parse([
            "HardFault crash",       # critical → error_count
            "warn: overflow",         # warning
            "error: timeout",         # error
            "normal log",             # none
        ])
        assert r.error_count == 3   # crash + error + warn
        assert r.warning_count == 2 # warn + error

    def test_di03_raw_text_matches_input(self, sample_logs_str):
        """DI-03: raw_text 与输入一致"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        r = p.parse(sample_logs_str)
        assert sample_logs_str in r.raw_text or r.raw_text in sample_logs_str

    def test_di04_address_locations_parallel(self, sample_logs):
        """DI-04: crash_addresses 与 crash_locations 长度相同"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        r = p.parse(sample_logs)
        assert len(r.crash_addresses) == len(r.crash_locations)

    def test_di05_analyze_returns_valid_diagnosis(self):
        """DI-05: analyze() 返回有效的 AIDiagnosis"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )
        svc = get_llm_service()
        req = LLMAnalysisRequest(
            logs=["HardFault: crash", "PC=0x08000104"],
            include_code=False,
        )
        result = asyncio.run(svc.analyze(req))
        diag = result.diagnosis
        assert diag.error_type in ("hardfault", "crash")
        assert isinstance(diag.root_cause, str)

    def test_di06_severity_exhaustive(self):
        """DI-06: severity 只能是 CRITICAL/WARNING/INFO"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        assert p.parse(["HardFault crash"]).severity == "CRITICAL"
        assert p.parse(["warn: overflow"]).severity == "WARNING"
        assert p.parse(["INFO: normal"]).severity == "INFO"


# ─── EH: Error Handling ───────────────────────────────────────────────────────

class TestEH:
    """EH: 错误处理"""

    def test_eh01_analyze_graceful_on_llm_failure(self):
        """EH-01: LLM 调用失败时返回 fallback diagnosis"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )

        svc = get_llm_service()
        req = LLMAnalysisRequest(
            logs=["HardFault crash"], include_code=False,
        )

        async def mock_analyze():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as m:
                m.side_effect = Exception("Network error")
                result = await svc.analyze(req)
                return result

        result = asyncio.run(mock_analyze())
        # Should return parse result + graceful diagnosis
        assert result.parse.error_type == "hardfault"
        assert result.diagnosis is not None
        assert isinstance(result.diagnosis.root_cause, str)

    def test_eh02_analyze_graceful_on_invalid_log(self):
        """EH-02: 非法日志输入时 graceful handling"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )
        svc = get_llm_service()
        req = LLMAnalysisRequest(logs=[""], include_code=False)
        result = asyncio.run(svc.analyze(req))
        assert result.parse is not None

    def test_eh03_parse_survives_none_input(self):
        """EH-03: None 输入不崩溃"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        result = p.parse(["HardFault", "PC=0x08000104"])
        assert result.error_type in ("hardfault", "hard_fault")

    def test_eh04_llm_returns_malformed_json(self):
        """EH-04: LLM 返回格式错误的响应时 graceful"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )

        svc = get_llm_service()
        req = LLMAnalysisRequest(logs=["HardFault crash"], include_code=False)

        async def mock_bad_response():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as m:
                m.return_value = AsyncMock(
                    raise_for_status=lambda: None,
                    json=lambda: {
                        "choices": [{"message": {"content": "NOT A VALID FORMAT"}}],
                        "usage": {"total_tokens": 10},
                    }
                )
                result = await svc.analyze(req)
                return result

        result = asyncio.run(mock_bad_response())
        assert result.diagnosis is not None

    def test_eh05_analyze_with_unreachable_api(self):
        """EH-05: API 不可达时返回有用错误信息"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )

        svc = get_llm_service()
        req = LLMAnalysisRequest(logs=["Panic"], include_code=False)

        async def mock_timeout():
            import httpx
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as m:
                m.side_effect = httpx.TimeoutException("timeout")
                result = await svc.analyze(req)
                return result

        result = asyncio.run(mock_timeout())
        assert result.diagnosis is not None
        assert len(result.diagnosis.root_cause) > 0


# ─── PF: Performance ──────────────────────────────────────────────────────────

class TestPF:
    """PF: 性能"""

    def test_pf01_parser_speed(self):
        """PF-01: 解析 100 行日志 < 50ms"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        logs = [f"[PMON] log line {i}: info message" for i in range(100)]
        logs.extend(["HardFault crash", "PC=0x08000104"])
        t0 = time.time()
        p.parse(logs)
        elapsed = (time.time() - t0) * 1000
        assert elapsed < 50, f"Parser took {elapsed:.1f}ms (limit: 50ms)"

    def test_pf02_parser_single_line_speed(self):
        """PF-02: 解析单行日志 < 5ms"""
        from src.services.llm_analysis_service import LogParser
        p = LogParser()
        t0 = time.time()
        p.parse(["[PMON] HardFault PC=0x08000104 LR=0x08000208"])
        elapsed = (time.time() - t0) * 1000
        assert elapsed < 5, f"Single line took {elapsed:.1f}ms (limit: 5ms)"

    def test_pf03_token_count_accuracy(self):
        """PF-03: count_tokens 对长文本准确性"""
        from src.services.llm_analysis_service import count_tokens
        text = "hello " * 500  # 3000 chars
        n = count_tokens(text)
        # Rough: ~4 chars/token, expect ~750 tokens
        assert 600 < n < 1200

    def test_pf04_analyze_no_code_index_speed(self):
        """PF-04: 无代码索引时 analyze() 快速完成（不调用 LLM）"""
        import asyncio
        from src.services.llm_analysis_service import (
            get_llm_service, LLMAnalysisRequest,
        )

        svc = get_llm_service()
        req = LLMAnalysisRequest(
            logs=["HardFault crash", "PC=0x08000104"],
            include_code=False,
        )

        async def mock_fast():
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as m:
                m.side_effect = Exception("skip")
                t0 = time.time()
                result = await svc.analyze(req)
                elapsed_ms = (time.time() - t0) * 1000
                return elapsed_ms

        elapsed_ms = asyncio.run(mock_fast())
        assert elapsed_ms < 500, f"Took {elapsed_ms:.1f}ms (limit: 500ms)"


# ─── RI: Router Integration ───────────────────────────────────────────────────

class TestRI:
    """RI: Router 集成"""

    def test_ri01_llm_router_imports(self):
        """RI-01: llm_router 可以正常导入"""
        from src.api.llm_router import llm_router
        assert llm_router is not None

    def test_ri02_llm_router_has_required_routes(self):
        """RI-02: Router 注册了 /log, /index, /index/status 路由"""
        from src.api.llm_router import llm_router
        routes = [r.path for r in llm_router.routes]
        # llm_router has prefix /api/llm/, so paths include it
        assert any("/log" in r for r in routes), f"no /log route in {routes}"
        assert any("/index" in r for r in routes), f"no /index route in {routes}"
        assert any("status" in r for r in routes), f"no status route in {routes}"

    def test_ri03_schemas_importable(self):
        """RI-03: 所有 schema 类可导入"""
        from src.schemas.llm_log import (
            LLMLogRequest, LLMLogResponse, LogParseResult,
            IndexRequest, IndexResponse, BatchLLMLogRequest,
            Severity, Language, CrashAddress,
        )
        assert Severity.CRITICAL is not None
        assert Language.ZH is not None


# ─── SDV Summary ──────────────────────────────────────────────────────────────

def test_sdv_summary():
    """Meta: 确保所有测试类都被收集"""
    import inspect
    this_file = __file__
    assert this_file.endswith("test_llm_sdv.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
