# backend/src/config.py
"""
Configuration management using Pydantic Settings.
All settings are loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── DeepSeek API ──────────────────────────────────────────────────────────
    deepseek_api_key: str = "sk-please-set-your-key"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ── Directories ──────────────────────────────────────────────────────────
    tftp_receive_dir: Path = Path("./tftp_receive")
    patches_dir: Path = Path("./patches")

    # Directories to index for LLM code retrieval (comma-separated)
    # e.g. "../,../../" means: sibling dir + project root
    code_index_dirs: str = "../,../../"

    # ── Server ───────────────────────────────────────────────────────────────
    http_port: int = 8000
    ws_port: int = 8765

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.tftp_receive_dir.mkdir(parents=True, exist_ok=True)
        self.patches_dir.mkdir(parents=True, exist_ok=True)

    @property
    def code_index_paths(self) -> list[str]:
        """Parse code_index_dirs into a list of paths."""
        return [p.strip() for p in self.code_index_dirs.split(",") if p.strip()]


settings = Settings()
