# backend/src/core/ai_engine/prompt_builder.py
"""
Build system and user prompts for the DeepSeek API from an ErrorContext.
Now also supports LogParseResult dataclass (duck typing).
"""

from __future__ import annotations
from typing import Any

from ...constants import SYSTEM_PROMPT
from ...schemas.log import ErrorContext


def build_prompts(ctx: ErrorContext) -> tuple[str, str]:
    """
    Return (system_prompt, user_prompt) strings ready for the API call.
    """
    user_content = (
        f"Analyze the following embedded Linux kernel log from device **{ctx.device}**.\n\n"
        f"{ctx.stack_trace}\n\n"
        f"Register dump:\n{ctx.register_dump}\n\n"
        f"Full context (surrounding log lines):\n" + "\n".join(f"  {l}" for l in ctx.surrounding_lines)
    )
    return SYSTEM_PROMPT, user_content


SYSTEM_PROMPT_LLM_LOG = """You are an expert embedded systems debugging assistant.

Your task is to analyze embedded system crash/error logs and:
1. Identify the ROOT CAUSE of the failure
2. Explain why it happened in technical detail
3. Suggest a FIX with specific code changes or configuration changes
4. Provide a CODE PATCH when possible

Output format (JSON in a code block):
```json
{
  "root_cause": "What went wrong and why",
  "ai_suggestion": "How to fix it, with specific steps",
  "code_patch": "Optional: exact code to apply",
  "confidence": 0.0-1.0
}
```

Be precise and technical. Reference specific register values, memory addresses,
and code locations when available.
"""

SYSTEM_PROMPT_LLM_LOG_ZH = """你是一个专业的嵌入式系统调试专家。

你的任务是分析嵌入式系统的崩溃/错误日志：
1. 识别故障的根本原因
2. 详细解释为什么会发生
3. 提供具体的修复建议（含代码修改或配置修改）
4. 在可能的情况下提供代码补丁

输出格式（JSON代码块）：
```json
{
  "root_cause": "问题原因（详细）",
  "ai_suggestion": "修复方法（含具体步骤）",
  "code_patch": "（可选）需要应用的代码",
  "confidence": 0.0-1.0
}
```

请保持技术精确性。在可能时引用具体的寄存器值、内存地址和代码位置。
"""


def build_log_analysis_prompt(
    ctx: Any,
    code_context: str,
    language: str = "auto",
) -> tuple[str, str]:
    """
    Build system and user prompts for LLM log analysis.

    Args:
        ctx: Parsed log result — accepts either ErrorContext (legacy) or
             LogParseResult dataclass (preferred). Duck-typed; accesses
             .raw_logs, .device, .error_type, .summary, .crash_addresses.
        code_context: Retrieved code snippets from local codebase
        language: Response language (auto/zh/en)

    Returns:
        (system_prompt, user_prompt)
    """
    # Accept both dataclass (LogParseResult) and Pydantic (ErrorContext)
    raw_logs: str = getattr(ctx, "raw_logs", None) or ""
    raw_logs_str: str = raw_logs if isinstance(raw_logs, str) else "\n".join(raw_logs)

    if language == "zh" or (language == "auto" and _looks_chinese(raw_logs_str)):
        system_prompt = SYSTEM_PROMPT_LLM_LOG_ZH
    else:
        system_prompt = SYSTEM_PROMPT_LLM_LOG

    # Build code context header
    if code_context and "/* No code" not in code_context:
        code_section = (
            "\n\n## 本地代码上下文\n"
            "以下是系统自动检索到的相关代码，请结合这些代码进行分析：\n\n"
            + code_context
        )
    else:
        code_section = (
            "\n\n## 本地代码上下文\n"
            "（未找到相关本地代码，请仅基于日志进行分析）"
        )

    # Build crash info — crash_addresses may be list[int]
    crash_addrs = getattr(ctx, "crash_addresses", []) or []
    crash_info = ""
    if crash_addrs:
        addrs = ", ".join(f"0x{a:08X}" for a in crash_addrs[:5])
        crash_info = f"\n\n## 崩溃地址\n{addrs}"

    # Language instruction
    lang_note = (
        "**请用中文回答**" if language == "auto" and _looks_chinese(raw_logs_str) else ""
    )

    # summary field
    summary_text = getattr(ctx, "summary", "") or ""
    device_name = getattr(ctx, "device", "") or "unknown"
    error_type_val = getattr(ctx, "error_type", "") or "unknown"

    user_content = (
        f"## 设备信息\n设备：{device_name}  |  错误类型：{error_type_val}\n\n"
        f"## 错误摘要\n{summary_text}\n\n"
        f"## 日志内容\n"
        + ("\n".join(f"  {i+1:2d}: {l}" for i, l in enumerate(raw_logs_str.splitlines()[:30])))
        + crash_info
        + code_section
        + f"\n\n{lang_note}"
    )

    return system_prompt, user_content


def _looks_chinese(text: str) -> bool:
    """Heuristic: guess if text is primarily Chinese."""
    import re
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    total = max(len(text), 1)
    return chinese / total > 0.15
