# backend/src/main.py
"""
PMON-AI-OPS Backend — FastAPI entry point.

Run locally:
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

Production:
    gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker \\
        --bind 0.0.0.0:8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.router import api_router
from .api.disasm_router import disasm_router
from .api.llm_router import llm_router
from .api.websocket import websocket_endpoint
from .config import settings
from .core.listener import start_watcher
from .core.notifier import ConnectionManager
from .services.pipeline import run_pipeline
from .utils.logger import logger


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      - Ensure TFTP + patches directories exist
      - Create asyncio.Queue and ConnectionManager (stored on app.state)
      - Start TFTP watcher task
      - Start processing pipeline task

    Shutdown:
      - Cancel both background tasks gracefully
    """
    logger.info("[Startup] Initialising PMON-AI-OPS backend…")

    # Ensure required directories
    settings.ensure_dirs()

    # Initialise shared state — both HTTP routes and WS handler access it via request.app.state
    queue: asyncio.Queue[object] = asyncio.Queue()
    ws_manager = ConnectionManager()
    app.state.queue = queue
    app.state.ws_manager = ws_manager

    # Start background workers
    watcher_task = asyncio.create_task(
        start_watcher(queue, settings.tftp_receive_dir),
        name="tftp-watcher",
    )
    pipeline_task = asyncio.create_task(
        run_pipeline(queue, settings, ws_manager),
        name="pipeline",
    )

    logger.info(
        f"[Startup] Watching {settings.tftp_receive_dir} | "
        f"DeepSeek={settings.deepseek_model} | log_level={settings.log_level}"
    )

    yield

    # ── Shutdown ────────────────────────────────────────────────────────────
    logger.info("[Shutdown] Stopping background tasks…")
    watcher_task.cancel()
    pipeline_task.cancel()
    try:
        await asyncio.gather(watcher_task, pipeline_task)
    except asyncio.CancelledError:
        pass
    logger.info("[Shutdown] Done")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="PMON-AI-OPS Backend",
    description="Embedded power monitor with AI-powered log analysis and WebSocket streaming",
    version="0.1.0",
    lifespan=lifespan,
)

# HTTP API routes: /api/health, /api/metrics, …
app.include_router(api_router)

# Disassembly routes: /api/disasm/upload, /api/disasm/resolve, …
app.include_router(disasm_router)

# LLM Log Analysis routes: /api/llm/log, /api/llm/index, …
app.include_router(llm_router)

# WebSocket route: /ws  (ConnectionManager accessed via request.app.state)
app.add_api_websocket_route("/ws", websocket_endpoint)
