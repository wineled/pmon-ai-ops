# backend/src/services/pipeline.py
"""
Main async processing pipeline: consume TFTPFileEvent from the queue,
run each stage, and broadcast results via WebSocket.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import Settings
from ..core.ai_engine import DeepSeekClient
from ..core.listener import TFTPFileEvent, extract_metrics, parse_log_file
from ..core.notifier import ConnectionManager, dispatch_alert, dispatch_metrics, dispatch_stream
from ..core.preprocessor import detect_error, enrich_error_context
from ..utils.logger import logger


async def run_pipeline(queue: asyncio.Queue[TFTPFileEvent], settings: Settings, ws_manager: ConnectionManager) -> None:
    """
    Run forever: pop a TFTPFileEvent from the queue, parse it,
    detect errors, call DeepSeek if needed, and broadcast all results.
    """
    deepseek = DeepSeekClient(settings)

    try:
        while True:
            event: TFTPFileEvent = await queue.get()
            file_path = Path(event.file_path)

            logger.info(f"[Pipeline] Processing {file_path.name} (device={event.device}, {event.size_bytes} bytes)")

            try:
                # 1. Parse log file → LogEntry list
                entries = parse_log_file(file_path)

                # 2. Dispatch stream event
                await dispatch_stream(ws_manager, event.device, event.size_bytes)

                # 3. Extract metrics and broadcast
                metrics_list = extract_metrics(entries)
                if metrics_list:
                    await dispatch_metrics(ws_manager, metrics_list)

                # 4. Detect errors
                error_ctx = detect_error(entries)
                if error_ctx:
                    # 5. Enrich with stack trace / register dump
                    error_ctx = enrich_error_context(error_ctx)

                    # 6. Call DeepSeek AI
                    diagnosis = await deepseek.analyze(error_ctx, settings)

                    # 7. Dispatch alert
                    await dispatch_alert(ws_manager, diagnosis, event.device)

                    logger.info(f"[Pipeline] Alert dispatched for {file_path.name}")

            except Exception as exc:
                logger.error(f"[Pipeline] Error processing {file_path.name}: {exc}")

            finally:
                queue.task_done()

    except asyncio.CancelledError:
        logger.info("[Pipeline] Shutting down")
        raise
    finally:
        await deepseek.close()
