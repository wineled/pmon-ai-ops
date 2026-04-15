# backend/src/core/preprocessor/normalizer.py
"""
Normalize a structured ErrorContext into a plain-text block
suitable for injection into an AI prompt.
"""

from ...schemas.log import ErrorContext


def normalize_for_ai(ctx: ErrorContext) -> str:
    """
    Serialize *ctx* into a compact, token-efficient string for the LLM.
    """
    sections = [
        f"[Device] {ctx.device}",
        f"[Error] {ctx.error_type}",
        f"[Time] {ctx.timestamp}",
        "",
        "--- Stack Trace ---",
        ctx.stack_trace or "(none)",
        "",
        "--- Register Dump ---",
        ctx.register_dump or "(none)",
        "",
        "--- Surrounding Lines ---",
        *ctx.surrounding_lines,
    ]
    return "\n".join(sections)
