# backend/src/core/ai_engine/cot_parser.py
"""
Parse the raw text response from DeepSeek into a structured AIDiagnosis.
"""

from ...schemas.alert import AIDiagnosis
from ...utils.diff_formatter import extract_diff_blocks
from ...utils.logger import logger


def parse_ai_response(raw: str, error_type: str) -> AIDiagnosis:
    """
    Parse *raw* text from DeepSeek into an AIDiagnosis.

    Expected format (flexible):
        ## ANALYSIS
        <root cause>

        ## DIFF
        ```diff
        ... unified diff ...
        ```
    """
    analysis_text = ""
    patch_content: str | None = None

    # Try the structured format first
    parts = raw.split("## DIFF", 1)
    if len(parts) == 2:
        analysis_text = parts[0].replace("## ANALYSIS", "").strip()
        diff_blocks = extract_diff_blocks(parts[1])
        patch_content = diff_blocks[0] if diff_blocks else None
    else:
        # Fallback: treat whole response as analysis
        analysis_text = raw.strip()

    # Extract root cause: first sentence of the analysis
    sentences = analysis_text.split(".")
    root_cause = sentences[0].strip() if sentences else analysis_text[:120]

    # Pick the first diff block if multiple were found
    if not patch_content:
        diff_blocks = extract_diff_blocks(raw)
        patch_content = diff_blocks[0] if diff_blocks else None

    logger.debug(f"[CoT] Root cause: {root_cause[:80]}")
    return AIDiagnosis(
        error_type=error_type,
        root_cause=root_cause,
        ai_suggestion=analysis_text,
        code_patch=patch_content,
    )
