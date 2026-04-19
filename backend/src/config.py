# backend/src/config.py
"""
Configuration management using Pydantic Settings.
All settings are loaded from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── DeepSeek API (兼容 OpenAI 格式) ───────────────────────────────────────
    deepseek_api_key: str = "sk-please-set-your-key"
    deepseek_base_url: str = "https://api.groq.com/openai/v1"  # Groq 免费 API
    deepseek_model: str = "llama-3.3-70b-versatile"  # Groq 免费模型

    # ── Directories ──────────────────────────────────────────────────────────
    tftp_receive_dir: Path = Path("./tftp_receive")
    patches_dir: Path = Path("./patches")

    # Directories to index for LLM code retrieval (comma-separated)
    # e.g. "../,../../" means: sibling dir + project root
    code_index_dirs: str = "../,../../"

    # ── Server ───────────────────────────────────────────────────────────────
    http_host: str = "0.0.0.0"
    http_port: int = 8000
    ws_host: str = "0.0.0.0"
    ws_port: int = 8765

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── AI Engine ────────────────────────────────────────────────────────────
    ai_max_retries: int = 3
    ai_initial_delay: float = 1.0  # seconds
    ai_timeout_seconds: float = 30.0
    ai_temperature: float = 0.2
    ai_max_tokens: int = 1024

    # ── TFTP Watcher ─────────────────────────────────────────────────────────
    tftp_max_wait_seconds: float = 5.0
    tftp_size_stable_threshold: float = 0.5
    tftp_min_file_size: int = 4

    # ── Code Index ───────────────────────────────────────────────────────────
    index_chunk_max_tokens: int = 512
    index_chunk_overlap: int = 50
    index_min_chunk_lines: int = 5

    # ── WebSocket ────────────────────────────────────────────────────────────
    ws_max_connections: int = 100
    ws_ping_interval: int = 30

    # ── Memory Service ───────────────────────────────────────────────────────
    memory_max_logs: int = 1000
    memory_max_alerts: int = 100

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        self.tftp_receive_dir.mkdir(parents=True, exist_ok=True)
        self.patches_dir.mkdir(parents=True, exist_ok=True)

    @property
    def code_index_paths(self) -> list[str]:
        """Parse code_index_dirs into a list of paths."""
        return [p.strip() for p in self.code_index_dirs.split(",") if p.strip()]


settings = Settings()
