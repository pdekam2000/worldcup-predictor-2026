"""Apply full provider utilization bundle to intelligence reports — Phase 46D."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from worldcup_predictor.domain.fixture import Fixture
from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.provider_utilization.advanced_match_intelligence import (
    build_advanced_match_intelligence,
)
from worldcup_predictor.intelligence.provider_utilization.models import ProviderUtilizationBundle
from worldcup_predictor.intelligence.provider_utilization.odds_movement_intelligence import (
    build_odds_movement_intelligence,
)
from worldcup_predictor.intelligence.provider_utilization.player_intelligence import build_player_intelligence
from worldcup_predictor.intelligence.provider_utilization.unified_event_layer import build_unified_event_layer
from worldcup_predictor.providers.sportmonks_consumption import SPORTMONKS_SUPPLEMENTAL_KEY

PROVIDER_UTILIZATION_KEY = "provider_utilization_v1"
ODDS_MOVEMENT_INTEL_KEY = "odds_movement_intelligence"
ADVANCED_MATCH_INTEL_KEY = "advanced_match_intelligence"
PLAYER_INTEL_KEY = "player_intelligence"
UNIFIED_EVENTS_KEY = "unified_events"


def _sportmonks_raw(report: MatchIntelligenceReport) -> dict[str, Any] | None:
    supplemental = getattr(report, "supplemental_sources", None) or {}
    sm = supplemental.get(SPORTMONKS_SUPPLEMENTAL_KEY) or {}
    if not isinstance(sm, dict):
        return None
    raw = sm.get("raw_fixture") or sm.get("field_map", {}).get("raw") or sm
    return raw if isinstance(raw, dict) else None


def _load_cached_unified_events(fixture_id: int) -> list[dict[str, Any]] | None:
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
        rows = repo.list_fixture_unified_events(fixture_id)
        repo.close()
        return rows if rows else None
    except Exception:
        return None


def _persist_unified_events(fixture_id: int, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    try:
        from worldcup_predictor.config.settings import get_settings
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
        repo.replace_fixture_unified_events(fixture_id, events)
        repo.close()
    except Exception:
        pass


def apply_provider_utilization(
    report: MatchIntelligenceReport,
    fixture: Fixture | None = None,
) -> MatchIntelligenceReport:
    """Extend report supplemental_sources with provider utilization bundle."""
    fixture_id = int(report.fixture_id)
    sm_raw = _sportmonks_raw(report)
    cached = _load_cached_unified_events(fixture_id)

    unified = build_unified_event_layer(
        fixture_id=fixture_id,
        api_football_events=report.fixture_events,
        sportmonks_raw=sm_raw,
        cached_events=cached,
    )

    if unified.events and not cached:
        _persist_unified_events(fixture_id, [e.to_dict() for e in unified.events])

    snapshots: list[dict[str, Any]] = []
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        snapshots = repo.fetch_odds_snapshots(fixture_id)
        repo.close()
    except Exception:
        snapshots = []

    supplemental = dict(getattr(report, "supplemental_sources", None) or {})
    _, odds_intel = build_odds_movement_intelligence(
        fixture_id=fixture_id,
        supplemental=supplemental,
        stored_snapshots=snapshots,
    )
    advanced = build_advanced_match_intelligence(report)
    player_intel = build_player_intelligence(report)

    bundle = ProviderUtilizationBundle(
        fixture_id=fixture_id,
        unified_events=unified,
        odds_movement=odds_intel,
        advanced_match=advanced,
        player_intelligence=player_intel,
        fusion_notes=[],
    )

    supplemental[PROVIDER_UTILIZATION_KEY] = bundle.to_dict()
    supplemental[UNIFIED_EVENTS_KEY] = unified.to_dict()
    supplemental[ODDS_MOVEMENT_INTEL_KEY] = odds_intel.to_dict()
    supplemental[ADVANCED_MATCH_INTEL_KEY] = advanced.to_dict()
    supplemental[PLAYER_INTEL_KEY] = player_intel.to_dict()

    sources = list(report.enrichment_sources or [])
    if "provider_utilization" not in sources:
        sources.append("provider_utilization")

    return replace(report, supplemental_sources=supplemental, enrichment_sources=sources)
