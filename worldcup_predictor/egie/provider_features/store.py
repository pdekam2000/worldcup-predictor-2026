"""EGIE Provider Feature Store — paid API fields per fixture (DB-only)."""

from __future__ import annotations

import json
import logging
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.config import PROVIDER_API_FOOTBALL
from worldcup_predictor.egie.provider_features.extractors import (
    load_sportmonks_fixture_raw,
    load_sqlite_xg_payload,
    parse_api_football_fixture_statistics,
    parse_injuries_payload,
    parse_lineups_payload,
    parse_odds_snapshots,
    parse_sportmonks_pressure,
    parse_xg_fields,
)
from worldcup_predictor.egie.provider_features.models import ProviderFeatureVector
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository

logger = logging.getLogger(__name__)


class EgieProviderFeatureStore:
    """Load paid-provider features for EGIE from SQLite + EGIE PostgreSQL raw store."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sqlite = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self.egie_raw = EgieRawStoreRepository(self.settings)

    def build(
        self,
        fixture_id: int,
        *,
        competition_key: str,
        home_team: str = "",
        away_team: str = "",
        recent_first_goal_home: float | None = None,
        recent_first_goal_away: float | None = None,
    ) -> ProviderFeatureVector:
        coverage: dict[str, bool] = {}
        sources: dict[str, str] = {}
        fields: dict[str, float | None] = {}

        # --- Odds (SQLite) ---
        snapshots = self.sqlite.fetch_odds_snapshots(int(fixture_id))
        odds = parse_odds_snapshots(snapshots)
        fields.update(odds)
        coverage["odds"] = odds.get("odds_implied_home") is not None
        if coverage["odds"]:
            sources["odds"] = "sqlite_odds_snapshots"

        # --- xG (SQLite snapshot -> Sportmonks EGIE raw -> file cache via payload) ---
        xg_raw = load_sqlite_xg_payload(self.sqlite, fixture_id)
        if xg_raw:
            sources["xg"] = "sqlite_xg_snapshots"
        else:
            xg_raw = load_sportmonks_fixture_raw(fixture_id, store=self.egie_raw)
            if xg_raw:
                sources["xg"] = "egie_sportmonks_raw"
        if xg_raw:
            fields.update(parse_xg_fields(xg_raw if isinstance(xg_raw, dict) else None))
            coverage["xg"] = fields.get("home_xg_for") is not None or fields.get("away_xg_for") is not None

        # --- Pressure (Sportmonks) ---
        sm_raw = xg_raw or load_sportmonks_fixture_raw(fixture_id, store=self.egie_raw)
        pressure = parse_sportmonks_pressure(sm_raw if isinstance(sm_raw, dict) else None)
        fields.update(pressure)
        coverage["pressure"] = (
            pressure.get("pressure_index_home") is not None
            or pressure.get("pressure_index_away") is not None
        )
        if coverage["pressure"]:
            sources["pressure"] = sources.get("xg", "egie_sportmonks_raw")

        # --- API-Football fixture statistics (EGIE PG) ---
        stat_row = self.egie_raw.get_latest_raw(
            provider=PROVIDER_API_FOOTBALL,
            resource_type="fixture_statistics",
            fixture_id=int(fixture_id),
        )
        if stat_row:
            stats = parse_api_football_fixture_statistics(stat_row.get("payload_json"))
            fields.update(stats)
            coverage["advanced_stats"] = any(
                stats.get(k) is not None
                for k in (
                    "home_shots",
                    "away_shots",
                    "home_shots_on_target",
                    "away_shots_on_target",
                    "home_dangerous_attacks",
                    "away_dangerous_attacks",
                )
            )
            if coverage["advanced_stats"]:
                sources["advanced_stats"] = "egie_api_football_fixture_statistics"

        # --- Lineups ---
        lineup_row = self.egie_raw.get_latest_raw(
            provider=PROVIDER_API_FOOTBALL,
            resource_type="lineups",
            fixture_id=int(fixture_id),
        )
        if lineup_row:
            lu = parse_lineups_payload(lineup_row.get("payload_json"))
            fields.update(lu)
            coverage["lineups"] = lu.get("lineup_strength_home") is not None
            if coverage["lineups"]:
                sources["lineups"] = "egie_api_football_lineups"

        # --- Injuries ---
        inj_row = self.egie_raw.get_latest_raw(
            provider=PROVIDER_API_FOOTBALL,
            resource_type="injuries",
            fixture_id=int(fixture_id),
        )
        if inj_row:
            inj = parse_injuries_payload(inj_row.get("payload_json"))
            fields.update(inj)
            coverage["injuries"] = inj.get("injuries_impact_home") is not None
            if coverage["injuries"]:
                sources["injuries"] = "egie_api_football_injuries"

        # --- Events presence ---
        ev_row = self.egie_raw.get_latest_raw(
            provider=PROVIDER_API_FOOTBALL,
            resource_type="events",
            fixture_id=int(fixture_id),
        )
        coverage["events"] = bool(ev_row) or bool(self.sqlite.list_fixture_goal_events(fixture_id))
        if ev_row:
            sources["events"] = "egie_api_football_events"

        return ProviderFeatureVector(
            fixture_id=int(fixture_id),
            competition_key=competition_key,
            home_xg_for=fields.get("home_xg_for"),
            away_xg_for=fields.get("away_xg_for"),
            home_xg_against=fields.get("home_xg_against"),
            away_xg_against=fields.get("away_xg_against"),
            pressure_index_home=fields.get("pressure_index_home"),
            pressure_index_away=fields.get("pressure_index_away"),
            home_shots=fields.get("home_shots"),
            away_shots=fields.get("away_shots"),
            home_shots_on_target=fields.get("home_shots_on_target"),
            away_shots_on_target=fields.get("away_shots_on_target"),
            home_dangerous_attacks=fields.get("home_dangerous_attacks"),
            away_dangerous_attacks=fields.get("away_dangerous_attacks"),
            odds_implied_home=fields.get("odds_implied_home"),
            odds_implied_away=fields.get("odds_implied_away"),
            odds_implied_draw=fields.get("odds_implied_draw"),
            odds_movement_home=fields.get("odds_movement_home"),
            lineup_strength_home=fields.get("lineup_strength_home"),
            lineup_strength_away=fields.get("lineup_strength_away"),
            injuries_impact_home=fields.get("injuries_impact_home"),
            injuries_impact_away=fields.get("injuries_impact_away"),
            recent_first_goal_home_rate=recent_first_goal_home,
            recent_first_goal_away_rate=recent_first_goal_away,
            coverage=coverage,
            sources=sources,
        )

    def audit_utilization(self, fixture_ids: list[int], *, competition_key: str) -> dict[str, Any]:
        """Summarize which paid fields are available across a fixture cohort."""
        totals = {k: 0 for k in ("xg", "pressure", "odds", "advanced_stats", "lineups", "injuries", "events")}
        n = len(fixture_ids)
        for fid in fixture_ids:
            vec = self.build(fid, competition_key=competition_key)
            for k in totals:
                if vec.coverage.get(k):
                    totals[k] += 1
        return {
            "fixtures": n,
            "coverage_pct": {k: round(100 * v / n, 2) if n else 0.0 for k, v in totals.items()},
            "coverage_count": totals,
        }
