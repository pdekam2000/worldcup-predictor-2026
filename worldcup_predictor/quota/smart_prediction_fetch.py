"""Priority-ordered intelligence fetch for predictions — Phase 40A."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.quota.local_first import (
    load_fixture_api_item_from_db,
    load_match_enrichment_from_db,
)
from worldcup_predictor.quota.quota_tracker import get_quota_tracker


class SmartPredictionFetcher:
    """
    Fetch only what is needed for prediction, in priority order:
    fixture → teams → odds → lineups → events.
    """

    def __init__(
        self,
        api_client: ApiFootballClient,
        builder: MatchIntelligenceBuilder | None = None,
    ) -> None:
        self._api = api_client
        self._builder = builder or MatchIntelligenceBuilder(api_client)

    def build(self, fixture_id: int, *, force_odds_api: bool = False) -> MatchIntelligenceReport:
        tracker = get_quota_tracker()
        repo = self._try_repo()

        # Priority 1 — fixture (local first)
        fixture: Fixture | None = None
        if repo is not None:
            local_items = load_fixture_api_item_from_db(repo, fixture_id)
            if local_items:
                tracker.record_local_hit()
                item = local_items[0]
                fixture = self._api.parse_fixture_item(item)
        if fixture is None:
            result = self._api.get_fixture_by_id(fixture_id)
            if result.ok and result.data:
                item = self._builder._extract_api_payload(result.data)  # noqa: SLF001
                if item is not None:
                    fixture = self._api.parse_fixture_item(item)

        if fixture is None:
            return self._builder.build_by_fixture_id(fixture_id, force_odds_api=force_odds_api)

        # Build with standard builder but skip deep enrichment when local cache covers it
        enrichment = None
        if repo is not None:
            enrichment = load_match_enrichment_from_db(repo, fixture_id)

        report = self._builder.build(fixture, force_odds_api=force_odds_api)

        if enrichment:
            tracker.record_local_hit()
            if enrichment.get("lineups") and report.lineups and not report.lineups.get("available"):
                report.lineups["available"] = True
                report.lineups["home"] = enrichment["lineups"]
            if enrichment.get("odds") and report.odds and not report.odds.available:
                report.odds.available = True
                report.odds.bookmakers = enrichment.get("odds") if isinstance(enrichment.get("odds"), list) else []
            if enrichment.get("events") and not report.fixture_events:
                report.fixture_events = enrichment["events"]

        return report

    @staticmethod
    def _try_repo():
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            return FootballIntelligenceRepository()
        except Exception:
            return None
