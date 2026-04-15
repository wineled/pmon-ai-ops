# backend/src/services/health.py
"""Health-check utilities for the service layer."""

from pathlib import Path

from ..config import settings
from ..utils.logger import logger


async def check_tftp_dir() -> tuple[bool, str]:
    """Check that TFTP receive directory exists and is writable."""
    path: Path = settings.tftp_receive_dir
    if not path.exists():
        return False, f"TFTP dir does not exist: {path}"
    if not path.is_dir():
        return False, f"TFTP path is not a directory: {path}"
    try:
        test_file = path / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
        return True, "OK"
    except PermissionError:
        return False, f"Permission denied writing to {path}"


async def check_deepseek_key() -> tuple[bool, str]:
    """Validate that the DeepSeek API key looks plausible."""
    import httpx

    key = settings.deepseek_api_key
    if not key or key == "sk-please-set-your-key":
        return False, "DEEPSEEK_API_KEY not set"
    if len(key) < 20:
        return False, f"DEEPSEEK_API_KEY looks too short (len={len(key)})"

    # Quick connectivity check — don't validate credentials, just reachability
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.deepseek_base_url}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.status_code in (200, 401):
                return True, "OK"  # 401 means key rejected but host is reachable
    except Exception as exc:
        return False, f"Cannot reach DeepSeek API: {exc}"

    return False, f"Unexpected status {resp.status_code}"


async def full_health_check() -> dict[str, dict]:
    """Run all health checks and return a structured dict."""
    tftp_ok, tftp_msg = await check_tftp_dir()
    ds_ok, ds_msg = await check_deepseek_key()
    return {
        "tftp_dir": {"ok": tftp_ok, "message": tftp_msg},
        "deepseek_api": {"ok": ds_ok, "message": ds_msg},
    }
