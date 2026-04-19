# backend/src/core/listener/tftp_watcher.py
"""
Watchdog-based TFTP receive directory watcher.

On every new file creation it waits for the write to complete
and then puts the file path into an asyncio.Queue consumed by the pipeline.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.observers import Observer

from ...constants import LOG_FILE_EXTENSIONS
from ...config import settings
from ...utils.logger import logger
from .models import TFTPFileEvent

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent

# ── Watchdog event handler ────────────────────────────────────────────────────


class TFTPHandler:
    """
    Watchdog handler that queues new log files for processing.

    Compatible with watchdog 6.x (requires dispatch method).
    Uses asyncio.run_coroutine_threadsafe() to safely schedule work
    from the watchdog thread into the main asyncio event loop.
    """

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
        self._queue = queue
        self._loop = loop

    def dispatch(self, event: FileSystemEvent) -> None:
        """Route to the appropriate on_* handler (required by watchdog 6.x)."""
        # event_type is a string in watchdog 6.x
        et = event.event_type if isinstance(event.event_type, str) else getattr(event.event_type, "value", str(event.event_type))
        if et == "created":
            self.on_created(event)
        elif et == "modified":
            self.on_modified(event)
        elif et == "moved":
            self.on_moved(event)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in LOG_FILE_EXTENSIONS:
            return
        logger.info(f"[TFTP] New file detected: {path.name}")
        # Schedule the coroutine from the watchdog thread into the asyncio event loop
        asyncio.run_coroutine_threadsafe(self._enqueue(path), self._loop)

    def on_modified(self, event: FileSystemEvent) -> None:
        pass

    def on_moved(self, event: FileSystemEvent) -> None:
        pass

    async def _enqueue(self, path: Path) -> None:
        """Wait for transfer completion then push onto the queue."""
        from ...utils.file_utils import wait_for_file_complete

        if not await wait_for_file_complete(path, stable_threshold=settings.tftp_size_stable_threshold):
            logger.warning(f"[TFTP] Skipping {path} - transfer incomplete")
            return

        try:
            device = path.stem.split("_")[0]  # e.g. "board01_20260415.log" -> "board01"
        except Exception:
            device = path.stem

        event = TFTPFileEvent(
            file_path=str(path.absolute()),
            device=device,
            size_bytes=path.stat().st_size,
        )
        await self._queue.put(event)
        logger.debug(f"[TFTP] Queued: {path.name} (device={device}, size={event.size_bytes})")


# ── Public API ────────────────────────────────────────────────────────────────


async def start_watcher(queue: asyncio.Queue, watch_dir: Path) -> None:
    """
    Start the watchdog observer and keep it running until cancelled.

    Parameters
    ----------
    queue : asyncio.Queue
        Queue onto which TFTPFileEvent objects are placed.
    watch_dir : Path
        Directory to watch (typically settings.tftp_receive_dir).
    """
    loop = asyncio.get_running_loop()
    handler = TFTPHandler(queue, loop)

    observer: Observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()
    logger.info(f"[TFTP] Watching {watch_dir}")

    try:
        while True:
            await asyncio.sleep(3600)  # sleep in 1-hour chunks so cancellation is responsive
    except asyncio.CancelledError:
        observer.stop()
        logger.info("[TFTP] Watcher stopped")
    finally:
        observer.join(timeout=5.0)
