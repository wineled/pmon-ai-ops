# backend/src/utils/file_utils.py
"""Utilities for safe file I/O: wait-for-write-complete and atomic read."""

import asyncio
from pathlib import Path

from .logger import logger


async def wait_for_file_complete(
    path: Path,
    min_size: int = 4,
    max_wait: float = 5.0,
    stable_threshold: float = 0.5,
) -> bool:
    """
    Poll a file until its size stops changing (transfer complete).

    Returns True when the file is stable and large enough.
    Returns False if the file never stabilises within *max_wait*.
    """
    deadline = asyncio.get_running_loop().time() + max_wait
    prev_size = -1
    stable_count = 0

    while asyncio.get_running_loop().time() < deadline:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            await asyncio.sleep(0.1)
            continue

        if size == prev_size and size >= min_size:
            stable_count += 1
            if stable_count >= 2:
                return True
        else:
            stable_count = 0

        prev_size = size
        await asyncio.sleep(stable_threshold)

    logger.warning(f"File {path} did not stabilise within {max_wait}s (size={prev_size})")
    return False


async def read_file_lines(path: Path) -> list[str]:
    """Read all lines from a file asynchronously using aiofiles."""
    try:
        import aiofiles  # type: ignore[import-untyped]

        async with aiofiles.open(path, encoding="utf-8", errors="replace") as f:
            content = await f.read()
        return content.splitlines()
    except Exception as exc:
        logger.error(f"Failed to read {path}: {exc}")
        return []
