from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.prediction import MultilingualText

logger = logging.getLogger(__name__)


class OpenAIClient:
    """
    Placeholder-ready OpenAI client for future PredictionAgent enrichment.

    Phase 1: no live calls; returns None and logs when unconfigured.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    @property
    def is_configured(self) -> bool:
        return self._settings.openai_configured

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self._settings.openai_api_key)
            except ImportError as exc:
                raise RuntimeError(
                    "openai package not installed. Add 'openai' to requirements when enabling predictions."
                ) from exc
        return self._client

    def generate_multilingual_summary(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> MultilingualText | None:
        """
        Generate localized analysis text. Returns None when unconfigured (Phase 1 default).
        """
        if not self.is_configured:
            logger.debug("OpenAI not configured; skipping generation")
            return None

        # Placeholder for Phase 2 — structured JSON multilingual output
        _ = (prompt, system_prompt)
        logger.info("OpenAI client ready but generation not implemented in Phase 1")
        return None

    def ping_connection(self) -> None:
        """Lightweight connectivity check compatible with OpenAI SDK v1+."""
        client = self._ensure_client()
        models = client.models.list()
        first = next(iter(models), None)
        if first is None:
            raise RuntimeError("OpenAI models list returned empty.")

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict | None:
        """Structured JSON completion for reasoning layer. Returns None when unconfigured or on error."""
        if not self.is_configured:
            logger.debug("OpenAI not configured; skipping JSON completion")
            return None

        try:
            client = self._ensure_client()
            response = client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            import json

            content = response.choices[0].message.content
            if not content:
                return None
            return json.loads(content)
        except Exception as exc:
            logger.warning("OpenAI JSON completion failed: %s", exc)
            return None
