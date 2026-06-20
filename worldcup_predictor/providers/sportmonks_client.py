"""SportmonksClient — unified WC fixture intelligence (Phase 22B)."""

from __future__ import annotations

import logging
from typing import Any

from worldcup_predictor.config.settings import Settings
from worldcup_predictor.providers.base import ProviderCallResult, ProviderTier
from worldcup_predictor.providers.sportmonks_enrichment import (
    resolve_unified_worldcup_fixture_intelligence,
)
from worldcup_predictor.providers.sportmonks_fixture_lookup import _match_fixture_item
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
        Unified fixture intelligence for enrichment.

        Phase 22B flow:
          1. SQLite cache by API-Football fixture ID (if warm)
          2. Date lookup (file cache) → Sportmonks fixture ID
          3. GET /fixtures/{id} with full includes (SQLite cache)
        """
        if not self.is_configured:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/unified",
                configured=False,
                error="SPORTMONKS_API_TOKEN or SPORTMONKS_API_KEY not configured",
            )

        if competition_key and competition_key != WORLD_CUP_2026_COMPETITION_KEY:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/unified",
                configured=True,
                error=None,
            )

        if api_fixture_id is None:
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/unified",
                configured=True,
                error="missing_api_fixture_id",
            )

        try:
            unified = resolve_unified_worldcup_fixture_intelligence(
                api_fixture_id=int(api_fixture_id),
                home_team=home_team,
                away_team=away_team,
                kickoff_date=kickoff_date,
                competition_key=competition_key,
                settings=self._settings,
            )
            trace = {
                "source_chain": list(unified.source_chain),
                "api_calls_made": unified.api_calls_made,
                "sportmonks_fixture_id": unified.sportmonks_fixture_id,
                "lookup_endpoint": unified.lookup_endpoint,
                "enrichment_endpoint": unified.enrichment_endpoint,
                "includes": list(unified.includes),
                "keys_present": list(unified.keys_present),
                "phase": "22B_unified",
            }
            if unified.success and unified.fixture:
                return ProviderCallResult(
                    data=unified.fixture,
                    provider="sportmonks",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=unified.endpoint_primary,
                    trace=trace,
                )
            if unified.source_chain and unified.source_chain[0] == "lookup_not_found":
                return ProviderCallResult(
                    data=None,
                    provider="sportmonks",
                    tier=ProviderTier.ENRICHMENT,
                    endpoint=unified.endpoint_primary,
                    error=None,
                    trace=trace,
                )
            token = self._settings.sportmonks_effective_token
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint=unified.endpoint_primary,
                error=redact_sportmonks_secrets(unified.message, token),
                trace=trace,
            )
        except Exception as exc:
            logger.exception("Sportmonks unified fixture intelligence failed")
            return ProviderCallResult(
                data=None,
                provider="sportmonks",
                tier=ProviderTier.ENRICHMENT,
                endpoint="fixtures/unified",
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
        for item in items:
            if isinstance(item, dict) and _match_fixture_item(
                item, home_team=home_team, away_team=away_team
            ):
                return item
        return None
