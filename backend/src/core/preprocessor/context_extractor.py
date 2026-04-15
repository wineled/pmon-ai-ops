# backend/src/core/preprocessor/context_extractor.py
"""
Extract rich context from an ErrorContext: stack trace, register dump,
and surrounding log lines. Mutates the ErrorContext in place.
"""

from ...constants import REGISTER_RE, STACK_TRACE_LINE_RE
from ...schemas.log import ErrorContext
from ...utils.logger import logger


def enrich_error_context(ctx: ErrorContext) -> ErrorContext:
    """
    Walk *ctx.surrounding_lines* and extract stack trace + register dump.
    Mutates and returns the same ErrorContext object.
    """
    stack_parts: list[str] = []
    reg_parts: list[str] = []

    for line in ctx.surrounding_lines:
        if STACK_TRACE_LINE_RE.match(line):
            stack_parts.append(line.strip())
        if REGISTER_RE.search(line):
            reg_parts.append(line.strip())

    ctx.stack_trace = "\n".join(stack_parts)
    ctx.register_dump = "\n".join(reg_parts)

    logger.debug(
        f"[Context] {ctx.device}/{ctx.error_type}: "
        f"{len(stack_parts)} stack lines, {len(reg_parts)} register lines"
    )
    return ctx
