# backend/src/utils/logger.py
"""Loguru configuration — colored structured output to stdout."""

import sys

from loguru import logger

# Remove the default handler added at import time
logger.remove()

# Add a pretty console handler
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> — <level>{message}</level>",
    level="INFO",
    colorize=True,
)

__all__ = ["logger"]
