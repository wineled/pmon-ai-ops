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
        "deepseek_model": settings.deepseek_model,
        "log_level": settings.log_level,
    }


@api_router.delete("/clear")
async def clear_all() -> dict[str, str]:
    """Clear all in-memory logs and alerts."""
    memory_service.clear()
    return {"status": "ok", "message": "Cleared"}


@api_router.post("/admin/reload-config")
async def reload_config() -> dict[str, str]:
    """Reload settings from .env (placeholder — actual reload logic goes here)."""
    logger.warning("[Admin] reload-config called (no-op in MVP)")
    return {"status": "ok", "message": "Config reload not yet implemented"}
