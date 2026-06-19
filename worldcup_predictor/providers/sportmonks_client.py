"""SportmonksClient — delegates fixture resolution to cache-first WC lookup."""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier
from worldcup_predictor.providers.sportmonks_fixture_lookup import lookup_world_cup_fixture
from worldcup_predictor.providers.sportmonks_provider import (
    WORLD_CUP_2026_COMPETITION_KEY,
    redact_sportmonks_secrets,
)

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
        api_fixture_id: int | None = None,
        competition_key: str | None = None,
    ) -> ProviderCallResult:
        """
        Lookup fixture context for enrichment.

        Uses GET /fixtures/date/{date} + fixtureLeagues:732 — not /fixtures/search.
        """
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/date",
                configured=False,
                error="SPORTMONKS_API_TOKEN or SPORTMONKS_API_KEY not configured",
            )

        if competition_key and competition_key != WORLD_CUP_2026_COMPETITION_KEY:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/date",
                configured=True,
                error=None,
            )

        if api_fixture_id is None:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/date",
                configured=True,
                error="missing_api_fixture_id",
            )

        try:
            lookup = lookup_world_cup_fixture(
                api_fixture_id=int(api_fixture_id),
                home_team=home_team,
                away_team=away_team,
                kickoff_date=kickoff_date,
                settings=self._settings,
            )
            if lookup.found and lookup.fixture:
                return ProviderCallResult(
                    data=lookup.fixture,
                    provider="sportmonks",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=lookup.endpoint,
                )
            if lookup.from_cache and lookup.reason == "not_found":
                return ProviderCallResult(
                    data=None,
                    provider="sportmonks",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=lookup.endpoint,
                    error=None,
                )
            if lookup.status_code and lookup.status_code >= 400:
                token = self._settings.sportmonks_effective_token
                return ProviderCallResult(
                    data=None,
                    provider="sportmonks",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=lookup.endpoint,
                    error=redact_sportmonks_secrets(lookup.reason, token),
                )
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint=lookup.endpoint,
                error=None,
            )
        except Exception as exc:
            logger.exception("Sportmonks fixture lookup failed")
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/date",
                error=redact_sportmonks_secrets(str(exc), self._settings.sportmonks_effective_token),
            )

    @staticmethod
    def _match_fixture(
        items: Any,
        home_team: str,
        away_team: str,
    ) -> dict[str, Any] | None:
        """Legacy helper — kept for tests importing _match_fixture."""
        if not isinstance(items, list):
            return None
        from worldcup_predictor.providers.sportmonks_fixture_lookup import _match_fixture_item

        for item in items:
            if isinstance(item, dict) and _match_fixture_item(
                item, home_team=home_team, away_team=away_team
            ):
                return item
        return None
