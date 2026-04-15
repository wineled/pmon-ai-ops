# backend/src/core/ai_engine/__init__.py
"""AI Engine package: DeepSeek client, prompt builder, CoT parser, patch generator."""

from .client import DeepSeekClient
from .cot_parser import parse_ai_response
from .patch_generator import generate_and_save_patch
from .prompt_builder import build_prompts

__all__ = ["DeepSeekClient", "build_prompts", "parse_ai_response", "generate_and_save_patch"]
