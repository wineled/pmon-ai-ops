# backend/src/core/preprocessor/error_detector.py
"""
Scan a list of LogEntry objects for fatal/kernel errors.
Returns an ErrorContext bundle for the first match, or None.
"""


from ...constants import KERNEL_OPS_RE, PANIC_RE, SEGFAULT_RE
from ...schemas.log import ErrorContext, LogEntry
from ...utils.logger import logger


def detect_error(entries: list[LogEntry]) -> ErrorContext | None:
    """
    Scan *entries* in order and return the first ErrorContext found.

    Detects: kernel oops, panic, segfault (see constants.py patterns).
    """
    error_lines: list[tuple[int, str]] = []

    for idx, entry in enumerate(entries):
        raw_upper = entry.raw.upper()
        error_type = ""

        if PANIC_RE.search(raw_upper):
            error_type = "Kernel Panic"
        elif KERNEL_OPS_RE.search(raw_upper):
            error_type = "Kernel Oops"
        elif SEGFAULT_RE.search(raw_upper):
            error_type = "Segfault"

        if error_type:
            # Mark this and collect a small window around it
            window = [e.raw for e in entries[max(0, idx - 5) : idx + 6]]
            error_lines.append((idx, entry.raw))

            ctx = ErrorContext(
                device=entry.device,
                error_type=error_type,
                first_line=entry.raw,
                surrounding_lines=window,
                timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
            )
            logger.warning(f"[Detector] {error_type} detected in {entry.device}: {entry.raw[:80]}")
            return ctx

    return None
