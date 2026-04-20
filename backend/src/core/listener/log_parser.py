# backend/src/core/listener/log_parser.py
"""
Parse raw log file lines into structured LogEntry objects.
Extracts timestamp, log level, and message from each line.
"""

import contextlib
from datetime import datetime
from pathlib import Path

from ...constants import CURRENT_RE, TEMP_RE, VOLTAGE_RE, WARNING_KEYWORDS
from ...schemas.log import LogEntry, MetricsData
from ...utils.logger import logger


def parse_log_file(file_path: Path) -> list[LogEntry]:
    """
    Parse every line in *file_path* into LogEntry objects.

    Handles common timestamp formats (ISO, syslog, epoch) and
    infers the log level from keywords.
    """
    entries: list[LogEntry] = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        logger.error(f"Failed to read {file_path}: {exc}")
        return []

    device = file_path.stem.split("_")[0] if "_" in file_path.stem else file_path.stem

    for idx, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue

        timestamp, level, message = _parse_line(stripped)
        entries.append(
            LogEntry(
                raw=raw,
                timestamp=timestamp,
                device=device,
                level=level,
                message=message,
                line_number=idx,
            )
        )

    logger.info(f"[Parser] {file_path.name}: {len(entries)} entries parsed")
    return entries


def _parse_line(line: str) -> tuple[datetime | None, str, str]:
    """Extract timestamp, level, and message from a single log line."""
    import re

    # ── Timestamp extraction ────────────────────────────────────────────────
    timestamp: datetime | None = None
    remaining = line

    # ISO format: 2026-04-15T00:00:00 or 2026/04/15 00:00:00
    ts_match = re.match(r"^(\d{4}[-/]\d{2}[-/]\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
    if ts_match:
        ts_str = ts_match.group(1).replace("/", "-").replace(" ", "T")
        try:
            timestamp = datetime.fromisoformat(ts_str)
        except ValueError:
            timestamp = None
        remaining = line[len(ts_match.group(0)) :].strip()

    # ── Level inference ─────────────────────────────────────────────────────
    level = "INFO"
    upper = remaining.upper()
    if any(k in upper for k in ["CRITICAL", "FATAL", "EMERGENCY"]):
        level = "CRITICAL"
    elif any(k in upper for k in ["ERROR", "PANIC", "OOPS", "BUG", "FAULT"]):
        level = "ERROR"
    elif any(k in upper for k in WARNING_KEYWORDS):
        level = "WARNING"
    elif any(k in upper for k in ["DEBUG", "TRACE", "VERBOSE"]):
        level = "DEBUG"

    # Remove common level prefixes: [INFO], <WARN>, INFO:
    remaining = re.sub(r"^\[[\w]+\]\s*|^<\w+>\s*|^[\w]+\s*[:|]\s*", "", remaining, flags=re.IGNORECASE)

    return timestamp, level, remaining


def extract_metrics(entries: list[LogEntry]) -> list[MetricsData]:
    """
    Walk through *entries* and extract voltage/current/temperature readings.
    Returns one MetricsData per file (last non-None values seen).
    """
    result: list[MetricsData] = []
    device_metrics: dict[str, dict] = {}

    for entry in entries:
        dm = device_metrics.setdefault(entry.device, {"voltage_mv": None, "current_ma": None, "temp_c": None})

        for pat, key in [(VOLTAGE_RE, "voltage_mv"), (CURRENT_RE, "current_ma"), (TEMP_RE, "temp_c")]:
            m = pat.search(entry.message)
            if m:
                with contextlib.suppress(ValueError):
                    dm[key] = float(m.group(1))

    for device, dm in device_metrics.items():
        if any(v is not None for v in dm.values()):
            result.append(MetricsData(device=device, **dm))

    return result
