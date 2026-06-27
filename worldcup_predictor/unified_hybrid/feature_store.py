"""Unified fixture feature store — Phase 61 (cache/DB only)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore


class UnifiedFixtureFeatureStore:
    """Aggregates provider + fixture features without live API calls."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sqlite = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self.provider = EgieProviderFeatureStore(self.settings)

    def build(
        self,
        fixture_id: int,
        *,
        competition_key: str = "",
        home_team: str = "",
        away_team: str = "",
    ) -> dict[str, Any]:
        row = self.sqlite.get_fixture_row(int(fixture_id)) or {}
        comp = competition_key or row.get("competition_key") or ""
        home = home_team or row.get("home_team") or ""
        away = away_team or row.get("away_team") or ""

        provider_vec = self.provider.build(
            int(fixture_id),
            competition_key=comp,
            home_team=home,
            away_team=away,
        )
        provider_fields = dict(getattr(provider_vec, "fields", {}) or {})
        coverage = dict(getattr(provider_vec, "coverage", {}) or {})
        sources = dict(getattr(provider_vec, "sources", {}) or {})

        stored = self.sqlite.get_worldcup_stored_prediction(int(fixture_id))
        stored_payload: dict[str, Any] = {}
        if stored and stored.get("payload_json"):
            try:
                stored_payload = json.loads(stored["payload_json"])
            except (json.JSONDecodeError, TypeError):
                stored_payload = {}

        freshness = {
            "provider_odds": sources.get("odds"),
            "provider_xg": sources.get("xg"),
            "provider_pressure": sources.get("pressure"),
            "stored_prediction_at": stored.get("updated_at") if stored else None,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

        quality_parts = [1.0 if coverage.get(k) else 0.0 for k in ("odds", "xg", "lineups", "injuries")]
        if stored_payload:
            quality_parts.append(1.0)
        else:
            quality_parts.append(0.3)
        data_quality = round(sum(quality_parts) / max(len(quality_parts), 1), 3)

        missing: list[str] = []
        if not coverage.get("odds"):
            missing.append("odds")
        if not coverage.get("xg"):
            missing.append("xg")
        if not stored_payload:
            missing.append("classic_prediction_cache")
        if not coverage.get("lineups"):
            missing.append("lineups")

        return {
            "fixture_id": int(fixture_id),
            "competition_key": comp,
            "home_team": home,
            "away_team": away,
            "kickoff_utc": row.get("kickoff_utc") or stored_payload.get("kickoff_utc"),
            "fixture_status": row.get("status") or stored_payload.get("fixture_status"),
            "provider_fields": provider_fields,
            "provider_coverage": coverage,
            "provider_sources": sources,
            "stored_classic_payload": stored_payload,
            "team_strength": {
                "home_xg_for": provider_fields.get("home_xg_for"),
                "away_xg_for": provider_fields.get("away_xg_for"),
                "home_xg_against": provider_fields.get("home_xg_against"),
                "away_xg_against": provider_fields.get("away_xg_against"),
            },
            "pressure": {
                "home": provider_fields.get("pressure_index_home"),
                "away": provider_fields.get("pressure_index_away"),
            },
            "odds_implied": {
                "home": provider_fields.get("odds_implied_home"),
                "draw": provider_fields.get("odds_implied_draw"),
                "away": provider_fields.get("odds_implied_away"),
            },
            "lineup_strength": {
                "home": provider_fields.get("lineup_strength_home"),
                "away": provider_fields.get("lineup_strength_away"),
            },
            "injuries_impact": {
                "home": provider_fields.get("injuries_impact_home"),
                "away": provider_fields.get("injuries_impact_away"),
            },
            "data_quality_score": data_quality,
            "feature_freshness": freshness,
            "missing_data_warnings": missing,
        }
