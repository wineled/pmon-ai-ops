# backend/src/api/deps.py
"""Dependency injection helpers for FastAPI routes."""

from ..config import Settings, settings

__all__ = ["get_settings"]


def get_settings() -> type[Settings]:
    """Return the global settings singleton for injection."""
    return Settings
