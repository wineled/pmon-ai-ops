# backend/src/utils/diff_formatter.py
"""Format C code blocks into unified diff format."""

from pathlib import Path

from .logger import logger


def extract_diff_blocks(text: str) -> list[str]:
    """
    Extract one or more ```diff / ```c blocks from raw AI response text.
    Falls back to searching for '---'/'+++' lines.
    """
    import re

    # Match ```diff ... ``` or ```c ... ```
    pattern = re.compile(
        r"```(?:diff|c)\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    blocks = pattern.findall(text)
    if blocks:
        return [b.strip() for b in blocks if b.strip()]

    # Fallback: raw unified diff lines
    lines = text.splitlines()
    diff_lines: list[str] = []
    in_diff = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("---") or stripped.startswith("+++"):
            in_diff = True
        if in_diff:
            diff_lines.append(line)
    return ["\n".join(diff_lines)] if diff_lines else []


def format_patch(filename: str, old_code: str, new_code: str) -> str:
    """
    Build a unified diff string for a single file.
    Used when the AI returns old_code / new_code separately.
    """
    import time

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    old_path = f"a/{filename}"
    new_path = f"b/{filename}"
    lines = [
        f"--- {old_path}\t{now}",
        f"+++ {new_path}\t{now}",
        f"@@ -1,{old_code.count(chr(10))+1} +1,{new_code.count(chr(10))+1} @@",
    ]
    for _i, line in enumerate(old_code.splitlines(), 1):
        lines.append(f"-{line}")
    for line in new_code.splitlines():
        lines.append(f"+{line}")
    return "\n".join(lines)


def save_patch(content: str, device: str, output_dir: Path) -> Path:
    """
    Write *content* to ``output_dir / {device}_{timestamp}.patch``.
    Returns the Path of the saved file.
    """
    import time

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_device = "".join(c if c.isalnum() else "_" for c in device)
    filename = f"{safe_device}_{ts}.patch"
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"Patch saved: {path}")
    return path
