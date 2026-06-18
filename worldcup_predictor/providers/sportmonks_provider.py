"""Sportmonks Football API v3 — World Cup 2026 enrichment provider (skeleton)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from worldcup_predictor.config.settings import Settings

logger = logging.getLogger(__name__)

# World Cup 2026 only — do not enable other leagues yet.
WORLD_CUP_2026_COMPETITION_KEY = "world_cup_2026"
WORLD_CUP_2026_LEAGUE_ID = 732
WORLD_CUP_2026_SEASON_ID = 26618

DEFAULT_BASE_URL = "https://api.sportmonks.com/v3/football"
DEFAULT_TIMEOUT_SECONDS = 20.0

_TOKEN_RE = re.compile(r"api_token=[^&\s]+", re.IGNORECASE)


@dataclass(frozen=True)
class SportmonksTestResult:
    """Result of a single cheap connectivity probe — no secrets."""

    connected: bool
    configured: bool
    status_code: int | None
    endpoint_path: str
    sample_count: int | None
    message: str


def redact_sportmonks_secrets(text: str, token: str = "") -> str:
    """Remove API tokens from URLs and error messages."""
    redacted = _TOKEN_RE.sub("api_token=***REDACTED***", text)
    if token:
        redacted = redacted.replace(token, "***REDACTED***")
    return redacted


class SportmonksProvider:
    """
    Complementary enrichment provider for FIFA World Cup 2026.

    API-Football remains primary. This client is not wired into agents yet.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = (settings.sportmonks_base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = float(settings.sportmonks_timeout_seconds)

    @property
    def is_configured(self) -> bool:
        return self._settings.sportmonks_configured

    @property
    def api_token(self) -> str:
        return self._settings.sportmonks_effective_token

    def safe_get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[int | None, Any | None, str | None]:
        """
        Safe GET — never raises. Token is passed as query param and redacted from errors.

        Returns (status_code, json_payload, error_message).
        """
        if not self.is_configured:
            return None, None, "SPORTMONKS_API_TOKEN not configured"

        token = self.api_token
        clean_path = path if path.startswith("/") else f"/{path}"
        query: dict[str, Any] = {"api_token": token}
        if params:
            query.update(params)

        url = f"{self._base_url}{clean_path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(url, params=query)
            status = response.status_code
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if status >= 400:
                detail = payload if isinstance(payload, dict) else response.text[:200]
                msg = redact_sportmonks_secrets(str(detail), token)
                return status, payload, f"HTTP {status}: {msg}"
            return status, payload, None
        except httpx.TimeoutException:
            return None, None, "request timed out"
        except httpx.HTTPError as exc:
            return None, None, redact_sportmonks_secrets(str(exc), token)
        except Exception as exc:
            logger.exception("Sportmonks request failed")
            return None, None, redact_sportmonks_secrets(str(exc), token)

    def run_world_cup_connectivity_test(self) -> SportmonksTestResult:
        """
        One cheap metadata request for World Cup league 732 — no bulk fetch.

        Endpoint: GET /leagues/{WORLD_CUP_2026_LEAGUE_ID}
        """
        endpoint_path = f"/leagues/{WORLD_CUP_2026_LEAGUE_ID}"

        if not self.is_configured:
            return SportmonksTestResult(
                connected=False,
                configured=False,
                status_code=None,
                endpoint_path=endpoint_path,
                sample_count=None,
                message="Set SPORTMONKS_API_TOKEN in .env to enable Sportmonks (World Cup 2026 only).",
            )

        status_code, payload, error = self.safe_get(endpoint_path)
        if error:
            return SportmonksTestResult(
                connected=False,
                configured=True,
                status_code=status_code,
                endpoint_path=endpoint_path,
                sample_count=None,
                message=error,
            )

        sample_count: int | None = None
        league_name = ""
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                sample_count = 1
                league_name = str(data.get("name") or "")
            elif isinstance(data, list):
                sample_count = len(data)

        message = f"World Cup league metadata OK ({league_name or 'league 732'})."
        return SportmonksTestResult(
            connected=True,
            configured=True,
            status_code=status_code,
            endpoint_path=endpoint_path,
            sample_count=sample_count,
            message=message,
        )
