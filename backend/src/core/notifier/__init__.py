# backend/src/core/notifier/__init__.py
"""Notifier package: WebSocket connection pool and message dispatcher."""

from .dispatcher import dispatch_alert, dispatch_metrics, dispatch_stream
from .manager import ConnectionManager

__all__ = ["ConnectionManager", "dispatch_alert", "dispatch_metrics", "dispatch_stream"]
