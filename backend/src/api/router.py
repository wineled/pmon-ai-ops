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


@api_router.post("/admin/reload-config")
async def reload_config() -> dict[str, str]:
    """Reload settings from .env (placeholder — actual reload logic goes here)."""
    logger.warning("[Admin] reload-config called (no-op in MVP)")
    return {"status": "ok", "message": "Config reload not yet implemented"}
