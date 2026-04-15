# backend/src/core/ai_engine/client.py
"""
Async DeepSeek API client with exponential-backoff retry (max 3 attempts).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ...config import Settings
from ...schemas.alert import AIDiagnosis
from ...schemas.log import ErrorContext
from ...utils.logger import logger
from .cot_parser import parse_ai_response
from .patch_generator import generate_and_save_patch
from .prompt_builder import build_prompts

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_RETRIES: int = 3
INITIAL_DELAY: float = 1.0  # seconds
TIMEOUT_SECONDS: float = 30.0


class DeepSeekClient:
    """HTTP client for the DeepSeek Chat API with built-in retry."""

    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=httpx.Timeout(TIMEOUT_SECONDS),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def analyze(self, ctx: ErrorContext, settings: Settings) -> AIDiagnosis:
        """
        Send *ctx* to DeepSeek and return a structured AIDiagnosis.
        Retries up to MAX_RETRIES times on 5xx / network errors.
        """
        system_prompt, user_prompt = build_prompts(ctx)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
        }

        delay = INITIAL_DELAY
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                client = await self._get_client()
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()

                raw_text = data["choices"][0]["message"]["content"]
                diagnosis = parse_ai_response(raw_text, ctx.error_type)

                # Save patch if present
                if diagnosis.code_patch:
                    generate_and_save_patch(diagnosis, ctx.device, settings.patches_dir)

                logger.info(
                    f"[DeepSeek] {ctx.device}/{ctx.error_type} → "
                    f"{diagnosis.root_cause[:60]} (attempt {attempt})"
                )
                return diagnosis

            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.warning(
                    f"[DeepSeek] HTTP {exc.response.status_code} on attempt {attempt}, "
                    f"retrying in {delay:.1f}s…"
                )
            except Exception as exc:  # network, JSON decode, etc.
                last_error = exc
                logger.warning(f"[DeepSeek] {type(exc).__name__}: {exc} on attempt {attempt}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2  # exponential backoff

        # All retries exhausted
        logger.error(f"[DeepSeek] All {MAX_RETRIES} attempts failed: {last_error}")
        return AIDiagnosis(
            error_type=ctx.error_type,
            root_cause="[AI analysis unavailable due to API errors]",
            ai_suggestion=f"DeepSeek API failed after {MAX_RETRIES} attempts: {last_error}",
        )
