# backend/src/core/ai_engine/patch_generator.py
"""
Save AI-generated patch content to disk.
"""

from pathlib import Path

from ...schemas.alert import AIDiagnosis
from ...utils.diff_formatter import save_patch
from ...utils.logger import logger


def generate_and_save_patch(
    diagnosis: AIDiagnosis,
    device: str,
    patches_dir: Path,
) -> Path | None:
    """
    If *diagnosis* carries a code_patch, write it to *patches_dir*.

    Returns the Path of the saved file, or None if no patch was present.
    """
    if not diagnosis.code_patch or diagnosis.code_patch.strip().upper() == "NONE":
        logger.debug(f"[Patch] No patch to save for {device}")
        return None

    path = save_patch(diagnosis.code_patch, device, patches_dir)
    return path
