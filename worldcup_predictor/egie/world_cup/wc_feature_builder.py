"""World Cup goal-timing feature snapshots — data layer only (no league-scope model change)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.egie.provider_features.store import EgieProviderFeatureStore
from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.aggregates import (
    accumulate_team_timing,
    league_baseline_timing,
    opponent_adjusted_features,
    recent_form_timing,
)
from worldcup_predictor.goal_timing.features.builder import FEATURE_VERSION

WC_FEATURE_VERSION = f"wc_phase62_{FEATURE_VERSION}"


def build_wc_timing_features(
    fixture_id: int,
    *,
    competition_key: str,
    stored: StoredGoalTimingAdapter | None = None,
    provider_store: EgieProviderFeatureStore | None = None,
    skip_provider: bool = False,
    as_of: datetime | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build EGIE-ready timing features for World Cup fixtures from stored history."""
    stored = stored or StoredGoalTimingAdapter()
    ctx = context or {}

    target = stored.get_target_fixture(fixture_id)
    if not target:
        return {
            "fixture_id": fixture_id,
            "competition_key": competition_key,
            "feature_version": WC_FEATURE_VERSION,
            "data_quality_score": 0.0,
            "unavailable_reason": "fixture_not_found",
        }

    kickoff_raw = target.get("kickoff_utc")
    as_of_dt = as_of or stored.parse_kickoff(kickoff_raw) or datetime.now(timezone.utc)
    before_iso = kickoff_raw or as_of_dt.isoformat()
    home_team = str(target.get("home_team") or ctx.get("home_team") or "Home")
    away_team = str(target.get("away_team") or ctx.get("away_team") or "Away")
    comp_key = str(competition_key or target.get("competition_key") or "")

    home_history = stored.team_history_before(
        home_team, before_kickoff=before_iso, competition_keys=[comp_key], limit=40
    )
    away_history = stored.team_history_before(
        away_team, before_kickoff=before_iso, competition_keys=[comp_key], limit=40
    )
    league_history = [
        stored._to_context(row, home_team)
        for row in stored.repo.list_finished_fixtures_before(
            before_kickoff=before_iso,
            competition_keys=[comp_key],
            limit=200,
        )
    ]

    home_feats = accumulate_team_timing(home_history, home_team)
    away_feats = accumulate_team_timing(away_history, away_team)
    home_recent = recent_form_timing(home_history, home_team)
    away_recent = recent_form_timing(away_history, away_team)
    league_base = league_baseline_timing(league_history)
    home_adj = opponent_adjusted_features(home_feats, away_feats)
    away_adj = opponent_adjusted_features(away_feats, home_feats)

    provider_vec = None
    if not skip_provider:
        try:
            provider_store = provider_store or EgieProviderFeatureStore(stored._settings)
            provider_vec = provider_store.build(
                fixture_id,
                competition_key=comp_key,
                home_team=home_team,
                away_team=away_team,
            )
        except Exception:
            provider_vec = None
    provider_features = provider_vec.to_dict() if provider_vec else None
    cov = (provider_vec.coverage or {}) if provider_vec else {}

    hs = home_feats.get("samples_with_goal_minute_data", 0) or 0
    aws = away_feats.get("samples_with_goal_minute_data", 0) or 0
    data_quality = min(1.0, 0.25 + 0.15 * min(hs, 10) / 10 + 0.15 * min(aws, 10) / 10)
    if cov.get("xg"):
        data_quality = min(1.0, data_quality + 0.15)
    if cov.get("odds"):
        data_quality = min(1.0, data_quality + 0.1)
    if cov.get("lineups"):
        data_quality = min(1.0, data_quality + 0.1)

    return {
        "fixture_id": fixture_id,
        "competition_key": comp_key,
        "as_of": as_of_dt.isoformat(),
        "home_team": home_team,
        "away_team": away_team,
        "match_date": kickoff_raw,
        "minute_ranges": list(GOAL_TIMING_MINUTE_RANGES),
        "feature_version": WC_FEATURE_VERSION,
        "team_goals_scored_by_range": {
            "home": home_feats.get("goals_scored_by_range"),
            "away": away_feats.get("goals_scored_by_range"),
        },
        "first_goal_team_distribution": {
            "home": home_feats.get("first_goal_team_distribution"),
            "away": away_feats.get("first_goal_team_distribution"),
        },
        "first_goal_minute_distribution": {
            "home": home_feats.get("first_goal_minute_distribution"),
            "away": away_feats.get("first_goal_minute_distribution"),
            "league": league_base.get("first_goal_minute_distribution"),
        },
        "recent_form_timing": {"home": home_recent, "away": away_recent},
        "opponent_adjusted": {"home": home_adj, "away": away_adj},
        "history_samples": {
            "home_matches": len(home_history),
            "away_matches": len(away_history),
            "league_matches": len(league_history),
            "home_with_goal_minutes": hs,
            "away_with_goal_minutes": aws,
        },
        "provider_features": provider_features,
        "data_quality_score": round(data_quality, 4),
        "provider_manifest": {
            "world_cup_phase62": True,
            "stored_fixtures": True,
            "provider_coverage": cov,
        },
    }
