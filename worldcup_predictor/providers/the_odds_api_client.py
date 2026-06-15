"""The Odds API provider — optional odds comparison / fill when API-Sports odds empty."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier

logger = logging.getLogger(__name__)


class TheOddsApiClient:
    """Optional odds comparison client (The Odds API v4)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.the_odds_api_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return self._settings.the_odds_api_configured

    def get_match_odds(
        self,
        *,
        home_team: str,
        away_team: str,
        sport_key: str | None = None,
    ) -> ProviderCallResult:
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint="odds",
                configured=False,
                error="THE_ODDS_API_KEY not configured",
            )

        sport = sport_key or self._settings.the_odds_api_sport
        endpoint = f"sports/{sport}/odds"
        params = {
            "apiKey": self._settings.the_odds_api_key,
            "regions": self._settings.the_odds_api_regions,
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
        }

        try:
            url = f"{self._base_url}/{endpoint}"
            with httpx.Client(timeout=25.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                events = response.json()
            matched = self._match_event(events, home_team, away_team)
            return ProviderCallResult(
                data=matched,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
            )
        except Exception as exc:
            logger.exception("The Odds API request failed")
            return ProviderCallResult(
                data=None,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=endpoint,
                error=str(exc),
            )

    @staticmethod
    def _match_event(
        events: Any,
        home_team: str,
        away_team: str,
    ) -> dict[str, Any] | None:
        if not isinstance(events, list):
            return None
        home_l = home_team.lower()
        away_l = away_team.lower()
        for event in events:
            if not isinstance(event, dict):
                continue
            eh = str(event.get("home_team", "")).lower()
            ea = str(event.get("away_team", "")).lower()
            if (home_l in eh or eh in home_l) and (away_l in ea or ea in away_l):
                return event
        return None
