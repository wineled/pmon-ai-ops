# backend/src/api/router.py
"""HTTP router: health, metrics, and admin endpoints."""

from fastapi import APIRouter, Request

from ..services.health import full_health_check
from ..utils.logger import logger

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok"}


@api_router.get("/health/deep")
async def deep_health() -> dict:
    """Full health check: TFTP dir + DeepSeek connectivity."""
    results = await full_health_check()
    overall = all(v["ok"] for v in results.values())
    return {"overall": "ok" if overall else "degraded", **results}


@api_router.get("/metrics")
async def metrics(request: Request) -> dict:
    """Return current runtime metrics."""
    ws_manager = request.app.state.ws_manager
    return {
        "ws_clients": ws_manager.active_count,
        "queue_size": request.app.state.queue.qsize(),
    }


from ..services.memory_service import memory_service

@api_router.get("/logs")
async def get_logs() -> dict:
    """Return recent log entries."""
    return {"logs": memory_service.get_recent_logs()}


@api_router.get("/alerts")
async def get_alerts() -> dict:
    """Return current alerts list."""
    return {"alerts": memory_service.get_alerts()}


@api_router.get("/config")
async def get_config(request: Request) -> dict:
    """Return system config (safe fields only)."""
    from ..config import settings
    return {
        "tftp_dir": str(settings.tftp_receive_dir),
        "patches_dir": str(settings.patches_dir),
        "code_index_dirs": settings.code_index_dirs,
        "deepseek_model": settings.deepseek_model,
        "deepseek_base_url": settings.deepseek_base_url,
        "http_host": settings.http_host,
        "http_port": settings.http_port,
        "ws_host": settings.ws_host,
        "ws_port": settings.ws_port,
        "log_level": settings.log_level,
        "ai_max_retries": settings.ai_max_retries,
        "ai_timeout_seconds": settings.ai_timeout_seconds,
        "memory_max_logs": settings.memory_max_logs,
        "memory_max_alerts": settings.memory_max_alerts,
    }


@api_router.delete("/clear")
async def clear_all() -> dict[str, str]:
    """Clear all in-memory logs and alerts."""
    memory_service.clear()
    return {"status": "ok", "message": "Cleared"}


@api_router.post("/admin/reload-config")
async def reload_config() -> dict[str, str]:
    """Reload settings from .env file."""
    from ..config import Settings
    global settings
    # Re-initialize settings to reload from .env
    settings = Settings()
    settings.ensure_dirs()
    logger.info("[Admin] Config reloaded from .env")
    return {"status": "ok", "message": "Config reloaded successfully"}
