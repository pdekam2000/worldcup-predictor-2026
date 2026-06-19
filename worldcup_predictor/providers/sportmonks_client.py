"""Sportmonks football provider — optional backup / enrichment (not primary)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier

logger = logging.getLogger(__name__)


class SportmonksClient:
    """Optional Sportmonks v3 football API client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.sportmonks_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return self._settings.sportmonks_configured

    def get_fixture_context(
        self,
        *,
        home_team: str,
        away_team: str,
        kickoff_date: str | None = None,
    ) -> ProviderCallResult:
        """
        Lookup fixture context for enrichment.

        Sportmonks fixture IDs differ from API-Sports — enrichment matches by
        team names (+ optional date window). Returns empty when not configured.
        """
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/search",
                configured=False,
                error="SPORTMONKS_API_TOKEN or SPORTMONKS_API_KEY not configured",
            )

        token = self._settings.sportmonks_effective_token
        params: dict[str, Any] = {
            "api_token": token,
            "include": "participants;statistics;scores",
        }
        if kickoff_date:
            params["filters"] = f"fixtureDate:{kickoff_date}"

        try:
            url = f"{self._base_url}/fixtures/search/{home_team}"
            with httpx.Client(timeout=25.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else payload
            matched = self._match_fixture(data, home_team, away_team)
            return ProviderCallResult(
                data=matched,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/search",
            )
        except Exception as exc:
            logger.exception("Sportmonks fixture lookup failed")
            from worldcup_predictor.providers.sportmonks_provider import redact_sportmonks_secrets

            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/search",
                error=redact_sportmonks_secrets(str(exc), self._settings.sportmonks_effective_token),
            )

    @staticmethod
    def _match_fixture(
        items: Any,
        home_team: str,
        away_team: str,
    ) -> dict[str, Any] | None:
        if not isinstance(items, list):
            return None
        home_l = home_team.lower()
        away_l = away_team.lower()
        for item in items:
            if not isinstance(item, dict):
                continue
            names = {
                str(p.get("name", "")).lower()
                for p in (item.get("participants") or [])
                if isinstance(p, dict)
            }
            if home_l in names and away_l in names:
                return item
        return None
