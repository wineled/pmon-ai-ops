# backend/tests/conftest.py
"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.core.listener.models import TFTPFileEvent
from src.schemas.alert import AIDiagnosis
from src.schemas.log import ErrorContext, LogEntry


@pytest.fixture
def sample_log_entries() -> list[LogEntry]:
    """A small list of LogEntry objects simulating a parsed kernel log."""
    return [
        LogEntry(
            raw="[2026-04-15 00:00:00] INFO  Board boot complete",
            device="board01",
            level="INFO",
            message="Board boot complete",
            line_number=1,
        ),
        LogEntry(
            raw="[2026-04-15 00:00:01] WARNING Watchdog timer reset",
            device="board01",
            level="WARNING",
            message="Watchdog timer reset",
            line_number=2,
        ),
        LogEntry(
            raw="[2026-04-15 00:00:02] CRITICAL kernel BUG at mm/slab.c:2847",
            device="board01",
            level="CRITICAL",
            message="kernel BUG at mm/slab.c:2847",
            line_number=3,
        ),
    ]


@pytest.fixture
def sample_error_context() -> ErrorContext:
    """A populated ErrorContext for a kernel BUG."""
    return ErrorContext(
        device="board01",
        error_type="Kernel BUG",
        first_line="kernel BUG at mm/slab.c:2847",
        stack_trace="[<c0012345>] kmalloc_order+0x18/0x2c\n[<c0056789>] alloc_pages_current+0xb0/0xd4",
        register_dump="r0: 0x00000000\nr1: 0x00000001",
        surrounding_lines=[
            "Modules linked in: pmon_core gpio_pwm",
            "CPU: 0 PID: 1234 Comm: kworker/0:1",
            "kernel BUG at mm/slab.c:2847",
            "Modules linked in: pmon_core gpio_pwm",
        ],
    )


@pytest.fixture
def sample_ai_diagnosis() -> AIDiagnosis:
    """A mock AI diagnosis with a tiny patch."""
    return AIDiagnosis(
        error_type="Kernel BUG",
        root_cause="kmalloc called with GFP_ATOMIC in interrupt context",
        ai_suggestion="Replace GFP_ATOMIC with GFP_KERNEL and move allocation outside ISR.",
        code_patch="--- a/mm/slab.c\n+++ b/mm/slab.c\n@@ -2844,7 +2844,7 @@\n     /* ... */\n-    obj = kmalloc(size, GFP_ATOMIC);\n+    obj = kmalloc(size, GFP_KERNEL);\n     /* ... */\n",
    )


@pytest.fixture
def temp_tftp_dir() -> Path:
    """A temporary directory that auto-cleans up."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_queue() -> asyncio.Queue:
    """A fresh asyncio.Queue for testing."""
    return asyncio.Queue()
