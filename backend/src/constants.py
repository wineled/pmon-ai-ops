# backend/src/constants.py
"""
Constants: regex patterns and keyword lists for log parsing and error detection.
"""

import re
from typing import Final

# ── Metrics Extraction ────────────────────────────────────────────────────────

VOLTAGE_RE: Final[re.Pattern] = re.compile(
    r"(?i)(?:voltage|vdd|vcc|power)\s*[:=]\s*([+-]?\d+\.?\d*)\s*(?:mv|millivolt)?",
    re.IGNORECASE,
)

CURRENT_RE: Final[re.Pattern] = re.compile(
    r"(?i)(?:current|amp|ma|milliam?p)\s*[:=]\s*([+-]?\d+\.?\d*)\s*(?:ma|milliam?p)?",
    re.IGNORECASE,
)

TEMP_RE: Final[re.Pattern] = re.compile(
    r"(?i)(?:temp|temperature|cpu_temp|die_temp)\s*[:=]\s*([+-]?\d+\.?\d*)\s*(?:c|cel|celsius|°c)?",
    re.IGNORECASE,
)

# ── Error Detection ─────────────────────────────────────────────────────────

# Kernel Oops / Panic / BUG patterns
KERNEL_OPS_RE: Final[re.Pattern] = re.compile(
    r"(?i)(?:kernel\s+oops|oops\s+#|BUG\s+\w+|------------\[ cut\ here \]------------)",
    re.IGNORECASE,
)

PANIC_RE: Final[re.Pattern] = re.compile(
    r"(?i)(?:kernel\s+panic|panic\s+at|fatal\s+exception|system\s+panic)",
    re.IGNORECASE,
)

SEGFAULT_RE: Final[re.Pattern] = re.compile(
    r"(?i)(?:segfault|segmentation\s+fault|signal\s+11|SIGSEGV|access\s+violation)",
    re.IGNORECASE,
)

# Stack trace lines: start with spaces + hex address
STACK_TRACE_LINE_RE: Final[re.Pattern] = re.compile(
    r"^\s+(?:[<[]?(0x[a-fA-F0-9]+)[>\]|[\w_]+[+]\d+|[\w_]+)\s+(.+)$"
)

# Register dump lines: "  r0: 0x..."
REGISTER_RE: Final[re.Pattern] = re.compile(
    r"^\s+([a-z0-9]{2,}):\s+(0x[a-fA-F0-9]+|[\da-fA-F]+)\b",
    re.IGNORECASE,
)

# ── Keyword Lists ─────────────────────────────────────────────────────────────

CRITICAL_KEYWORDS: Final[list[str]] = [
    "panic",
    "oops",
    "bug",
    "fault",
    "die",
    "fatal",
    "critical error",
    "emergency",
    "system halt",
    "watchdog timeout",
    "hard lockup",
    "soft lockup",
]

WARNING_KEYWORDS: Final[list[str]] = [
    "error",
    "fail",
    "timeout",
    "retry",
    "warning",
    "overflow",
    "underflow",
    "corrupt",
    "invalid",
    "unrecoverable",
]

INFO_KEYWORDS: Final[list[str]] = [
    "info",
    "notice",
    "debug",
    "trace",
    "verbose",
]

# ── AI Prompt Templates ───────────────────────────────────────────────────────

SYSTEM_PROMPT: Final[str] = (
    "You are an embedded Linux kernel expert. "
    "Analyze the following kernel Oops/Panic log and provide:\n"
    "1. Root cause analysis (brief, 2-3 sentences)\n"
    "2. A C code fix suggestion in unified diff format (---/+++)\n\n"
    "Respond using exactly this structure:\n"
    "## ANALYSIS\n"
    "<your reasoning>\n"
    "## DIFF\n"
    "<your diff here, or NONE if no patch needed>"
)

# ── TFTP File Patterns ────────────────────────────────────────────────────────

LOG_FILE_EXTENSIONS: Final[set[str]] = {".log", ".txt", ".dmp", ".core"}
MIN_FILE_SIZE_BYTES: Final[int] = 4
MAX_WAIT_SECONDS: Final[float] = 5.0
SIZE_STABLE_THRESHOLD_SECONDS: Final[float] = 0.5
