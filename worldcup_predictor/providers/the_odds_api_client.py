"""The Odds API provider — backward-compatible client wrapper (Phase 50B)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier
from worldcup_predictor.providers.the_odds_api_provider import TheOddsApiProvider


class TheOddsApiClient:
    """Optional odds comparison client — delegates to TheOddsApiProvider."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = TheOddsApiProvider(settings)

    @property
    def is_configured(self) -> bool:
        return self._provider.is_configured

    def get_match_odds(
        self,
        *,
        home_team: str,
        away_team: str,
        sport_key: str | None = None,
        kickoff_utc: Any | None = None,
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

        from datetime import datetime, timezone

        fixture = Fixture(
            id=0,
            competition_key="world_cup_2026",
            home_team=home_team,
            away_team=away_team,
            kickoff_utc=kickoff_utc or datetime.now(timezone.utc),
            venue="TBD",
            stage="Group",
            league_id=1,
            season=2026,
        )
        if sport_key:
            self._settings.the_odds_api_sport = sport_key

        result = self._provider.fetch_for_fixture(fixture, allow_live=True, fallback_sport_odds=True)
        if result.event:
            return ProviderCallResult(
                data=result.event,
                provider="the_odds_api",
                tier=ProviderTier.ENRICHMENT,
                endpoint=result.endpoint or "odds",
            )
        return ProviderCallResult(
            data=None,
            provider="the_odds_api",
            tier=ProviderTier.ENRICHMENT,
            endpoint=result.endpoint or "odds",
            error=result.error or "no_matching_event",
        )
