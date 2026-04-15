# backend/src/api/deps.py
"""Dependency injection helpers for FastAPI routes."""

from ..config import settings

__all__ = ["get_settings"]


def get_settings() -> type[settings.__class__]:
    """Return the global settings singleton for injection."""
    return settings.__class__
