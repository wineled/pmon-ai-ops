# backend/src/core/ai_engine/prompt_builder.py
"""
Build system and user prompts for the DeepSeek API from an ErrorContext.
"""

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
