# backend/src/core/listener/models.py
"""Models used internally by the TFTP listener module."""

from pydantic import BaseModel, Field


class TFTPFileEvent(BaseModel):
    """Event emitted when a new file is detected in the TFTP receive directory."""

    file_path: str = Field(..., description="Absolute path to the new file")
    device: str = Field(default="unknown", description="Device identifier from filename")
    size_bytes: int = Field(default=0)
