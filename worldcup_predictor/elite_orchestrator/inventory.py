"""Part A — catalogue validated prediction components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_orchestrator.models import REJECTED_COMPONENTS, ComponentRecord

ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_validated_inventory() -> list[ComponentRecord]:
    """Return only research-validated components approved for elite orchestration."""
    return [
        ComponentRecord(
            component_id="lineup_intelligence",
            name="Lineup Intelligence",
            purpose="Expected/confirmed lineups, starter probability, lineup quality per team",
            confidence="HIGH_VALUE",
            supported_markets=("first_goal_team", "team_to_score_first", "anytime_goalscorer", "first_goalscorer"),
            data_dependencies=("sportmonks_lineups_cache", "fs_player_rolling_features", "expected_lineup_store"),
            latency_ms=120,
            readiness="READY",
            status="validated",
            phase_source="54J / 54S / 24A",
            package_path="worldcup_predictor/feature_store/player_store",
            notes="Lineup-only beats lineup+availability on UEFA (54S). Core eligibility gate for goalscorer.",
        ),
        ComponentRecord(
            component_id="player_form_store",
            name="Player Form Store",
            purpose="Rolling goals/xG/form, minutes, starter history at kickoff",
            confidence="HIGH_VALUE",
            supported_markets=("anytime_goalscorer", "first_goalscorer", "first_goal_team"),
            data_dependencies=("fs_player_match_stats", "fs_player_rolling_features", "player_store_cache"),
            latency_ms=80,
            readiness="READY",
            status="validated",
            phase_source="54J / 54L",
            package_path="worldcup_predictor/feature_store/player_store",
            notes="Form + goals_per_90 primary signal. 57.1% composite top-3 anytime (54Q).",
        ),
        ComponentRecord(
            component_id="goalscorer_intelligence",
            name="Goalscorer Intelligence Engine",
            purpose="Per-fixture player ranking for anytime/first goalscorer markets",
            confidence="HIGH_VALUE",
            supported_markets=("anytime_goalscorer", "first_goalscorer", "first_goal_team"),
            data_dependencies=("player_form_store", "lineup_intelligence", "goalscorer_dataset_v3"),
            latency_ms=200,
            readiness="PARTIAL",
            status="validated",
            phase_source="54K / 54L / 54Q",
            package_path="worldcup_predictor/egie/goalscorer_shadow",
            notes="Top-3 anytime 57.1% overall; WC 77.1%. UEFA odds coverage 3% blocks elite path.",
        ),
        ComponentRecord(
            component_id="first_goal_team_v2",
            name="First Goal Team Engine V2",
            purpose="Team-level first-goal prediction using goalscorer intel + baseline proxies",
            confidence="HIGH_VALUE",
            supported_markets=("first_goal_team", "team_to_score_first"),
            data_dependencies=("expanded_egie_dataset", "goalscorer_dataset_v3", "sportmonks_odds_cache"),
            latency_ms=150,
            readiness="READY",
            status="validated",
            phase_source="55C",
            package_path="worldcup_predictor/egie/first_goal_team_v2",
            notes="Best group baseline_goalscorer 54.6%. Beats 51H production 50.8%. Below 54F-7 xG 58.3%.",
        ),
        ComponentRecord(
            component_id="market_behavior_intelligence",
            name="Market Behavior Intelligence (MBI)",
            purpose="Historical odds-bucket calibration priors for MW and O/U",
            confidence="MEDIUM_VALUE",
            supported_markets=("1x2", "first_goal_team", "team_to_score_first"),
            data_dependencies=("odds_snapshots", "sportmonks_odds_cache", "oddalerts_odds_history"),
            latency_ms=60,
            readiness="PARTIAL",
            status="validated",
            phase_source="56A",
            package_path="worldcup_predictor/mbi",
            notes="10% prior blend +0.0025 Brier on MW/O/U. Shadow prior only — not standalone edge.",
        ),
        ComponentRecord(
            component_id="odds_intelligence",
            name="Odds Intelligence",
            purpose="Match winner, FTS, O/U implied probs, movement, sharp/soft consensus",
            confidence="BASELINE",
            supported_markets=("1x2", "first_goal_team", "team_to_score_first", "anytime_goalscorer"),
            data_dependencies=("sportmonks_odds_cache", "odds_snapshots", "api_football_odds"),
            latency_ms=90,
            readiness="PARTIAL",
            status="validated",
            phase_source="API-K / 54C2",
            package_path="worldcup_predictor/egie/uefa_club/odds_intelligence.py",
            notes="UEFA MW coverage ~57%. WC goalscorer odds 100%. FTS sparse in strict UEFA cache.",
        ),
        ComponentRecord(
            component_id="egie_historical_baseline",
            name="EGIE Historical Baseline",
            purpose="Production goal-timing engine — first goal team, range, minute",
            confidence="BASELINE",
            supported_markets=("first_goal_team", "team_to_score_first", "goal_timing"),
            data_dependencies=("egie_postgres_raw", "sqlite_fixtures", "goal_events"),
            latency_ms=250,
            readiness="READY",
            status="baseline",
            phase_source="51H",
            package_path="worldcup_predictor/egie",
            notes="PL backtest FGT 50.8%. Production anchor — elite layer wraps, does not replace.",
        ),
        ComponentRecord(
            component_id="hybrid_confidence_engine",
            name="Hybrid Confidence Engine",
            purpose="Per-market Tier A–D confidence from survival + DQ + reliability priors",
            confidence="PRODUCTION_ACTIVE",
            supported_markets=("first_goal_team", "goal_timing"),
            data_dependencies=("egie_survival_outputs", "reliability_prior_store"),
            latency_ms=40,
            readiness="READY",
            status="baseline",
            phase_source="52D",
            package_path="worldcup_predictor/egie/confidence",
            notes="Tier A–D mapping exists. Extend to goalscorer + 1X2 in shadow fusion.",
        ),
    ]


def build_rejected_inventory() -> list[dict[str, Any]]:
    """Document rejected/low-value components excluded from orchestration."""
    rejected = [
        {
            "component_id": "pressure_index",
            "phase": "54H-7",
            "recommendation": "PRESSURE_NO_VALUE",
            "reason": "Pre-match pressure adds no value; in-play only signal.",
        },
        {
            "component_id": "team_context",
            "phase": "54R",
            "recommendation": "GOALSCORER_HIGH_VALUE but excluded",
            "reason": "Team context hurts UEFA (−1.9pp). Only is_home positive.",
        },
        {
            "component_id": "availability_overlay",
            "phase": "54S",
            "recommendation": "GOALSCORER_HIGH_VALUE but excluded",
            "reason": "Lineup-only (67.2%) beats lineup+availability (66.2%) on UEFA.",
        },
        {
            "component_id": "team_xg_general",
            "phase": "54F / 54F-6 / 54F-7",
            "recommendation": "NO_VALUE / market-specific only",
            "reason": "General xG blend hurts FGT. Market-specific xG kept as reference only.",
        },
        {
            "component_id": "full_feature_blend",
            "phase": "55C / 54S",
            "recommendation": "rejected",
            "reason": "Full blends plateau or degrade vs focused feature families.",
        },
    ]
    return [r for r in rejected if r["component_id"] in REJECTED_COMPONENTS]


def inventory_summary(components: list[ComponentRecord]) -> dict[str, Any]:
    return {
        "validated_count": len(components),
        "rejected_count": len(REJECTED_COMPONENTS),
        "by_readiness": {
            level: sum(1 for c in components if c.readiness == level)
            for level in ("READY", "PARTIAL", "RESEARCH", "BLOCKED")
        },
        "by_confidence": {
            c.confidence: sum(1 for x in components if x.confidence == c.confidence)
            for c in components
        },
    }
