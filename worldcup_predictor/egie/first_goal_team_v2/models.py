"""Phase 55C First Goal Team Engine V2 models."""

from __future__ import annotations

from typing import Literal

BASELINE_FEATURES: tuple[str, ...] = (
    "home_goal_rate_proxy",
    "away_goal_rate_proxy",
    "data_quality_score",
    "home_history_samples",
    "away_history_samples",
)

LINEUP_FEATURES: tuple[str, ...] = (
    "home_starter_count",
    "away_starter_count",
    "home_avg_starter_probability",
    "away_avg_starter_probability",
    "home_lineup_quality",
    "away_lineup_quality",
)

GOALSCORER_INTEL_FEATURES: tuple[str, ...] = (
    "home_top_goals_per_90",
    "away_top_goals_per_90",
    "home_top_xg_per_90",
    "away_top_xg_per_90",
    "home_top_recent_form",
    "away_top_recent_form",
    "goalscorer_intel_gap",
)

FTS_ODDS_FEATURES: tuple[str, ...] = (
    "fts_implied_home",
    "fts_implied_away",
    "mw_implied_home",
    "mw_implied_away",
    "mw_implied_draw",
    "odds_movement_home",
    "odds_movement_away",
)

XG_FEATURES: tuple[str, ...] = (
    "home_recent_xg",
    "away_recent_xg",
    "xg_difference",
    "rolling_xg_5_home",
    "rolling_xg_5_away",
)

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "baseline": BASELINE_FEATURES,
    "baseline_lineups": BASELINE_FEATURES + LINEUP_FEATURES,
    "baseline_goalscorer": BASELINE_FEATURES + GOALSCORER_INTEL_FEATURES,
    "baseline_fts_odds": BASELINE_FEATURES + FTS_ODDS_FEATURES,
    "full_blend": BASELINE_FEATURES + LINEUP_FEATURES + GOALSCORER_INTEL_FEATURES + FTS_ODDS_FEATURES + XG_FEATURES,
}

TARGET_COL = "target_home_first_goal"
BASELINE_54F7_ACCURACY = 0.5833
GOALSCORER_INTEL_BASELINE_ACCURACY = 0.5076

VALID_RECOMMENDATIONS = frozenset(
    {
        "FIRST_GOAL_TEAM_HIGH_VALUE",
        "FIRST_GOAL_TEAM_ELITE_PATH",
        "FIRST_GOAL_TEAM_NO_VALUE",
    }
)

TierLabel = Literal["A", "B", "C", "D"]
