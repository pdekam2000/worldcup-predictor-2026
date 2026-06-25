"""Shadow Pressure Feature Store design (Phase 54G — proposal only, not implemented)."""

from __future__ import annotations

from typing import Any


def shadow_feature_store_design() -> dict[str, Any]:
    return {
        "status": "design_only",
        "pipeline": [
            "Sportmonks GET /fixtures/{id}?include=pressure;participants;events.type",
            "Pressure Raw Store (JSONL per fixture, immutable)",
            "Pressure Normalizer (minute-participant rows → canonical schema)",
            "Aggregation Engine (pre-match rolling + in-match live windows)",
            "EGIE Shadow Arm (market-specific routing, no WDE)",
        ],
        "storage_layers": {
            "raw": "data/feature_store/sportmonks_pressure/raw/{fixture_id}.json",
            "normalized": "data/feature_store/sportmonks_pressure/normalized/{fixture_id}.parquet",
            "aggregates": "data/feature_store/sportmonks_pressure/aggregates/team_rolling.parquet",
            "shadow": "data/shadow/pressure_promotion_shadow.jsonl",
        },
        "canonical_schema": {
            "fixture_id": "int",
            "participant_id": "int",
            "team_id": "int (resolved via participants)",
            "minute": "int (0–120+)",
            "pressure_value": "float",
            "kickoff_utc": "datetime",
            "league_id": "int",
            "is_live": "bool",
        },
        "proposed_features": [
            {
                "name": "rolling_pressure_5",
                "description": "Mean pressure last 5 minutes per team (pre-match: prior fixture avg)",
                "markets": ["first_goal_team", "next_goal_team"],
            },
            {
                "name": "pressure_momentum",
                "description": "Slope of pressure over last 10 minutes",
                "markets": ["live_goal_probability", "next_goal_team"],
            },
            {
                "name": "pressure_acceleration",
                "description": "Second derivative of pressure timeline",
                "markets": ["goal_minute", "live_goal_probability"],
            },
            {
                "name": "pressure_dominance",
                "description": "Share of total match pressure per team",
                "markets": ["first_goal_team", "team_goals"],
            },
            {
                "name": "pressure_attack_ratio",
                "description": "pressure / dangerous_attacks from statistics",
                "markets": ["goal_range", "team_goals"],
            },
            {
                "name": "pressure_swing",
                "description": "Max minute-to-minute delta between teams",
                "markets": ["next_goal_team", "live_goal_probability"],
            },
            {
                "name": "pressure_spike_count",
                "description": "Count of minutes with pressure > P90 team baseline",
                "markets": ["goal_minute", "goal_range"],
            },
            {
                "name": "dangerous_attack_ratio",
                "description": "Dangerous attacks share from statistics block",
                "markets": ["goal_range", "pressure_attack_ratio"],
            },
        ],
        "market_routing": {
            "first_goal_team": ["rolling_pressure_5", "pressure_dominance"],
            "goal_minute": ["pressure_momentum", "pressure_spike_count", "pressure_acceleration"],
            "goal_range": ["pressure_attack_ratio", "dangerous_attack_ratio"],
            "next_goal_team": ["pressure_momentum", "pressure_swing", "rolling_pressure_5"],
            "team_goals": ["pressure_dominance", "pressure_attack_ratio"],
            "live_goal_probability": ["pressure_momentum", "pressure_swing", "pressure_acceleration"],
        },
        "exclusions": {
            "first_goal_team": "Do not mix with xG full stack (54F-7 NO_XG policy independent)",
            "production": "Shadow replay only until Phase 54G+ validation passes",
        },
        "integration_point": "worldcup_predictor/egie/provider_features/extractors.py → parse_sportmonks_pressure (replace statistics proxy)",
    }
