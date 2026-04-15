# backend/src/core/preprocessor/__init__.py
"""Preprocessor package: error detection, context extraction, normalization."""

from .context_extractor import enrich_error_context
from .error_detector import detect_error
from .normalizer import normalize_for_ai

__all__ = ["detect_error", "enrich_error_context", "normalize_for_ai"]
