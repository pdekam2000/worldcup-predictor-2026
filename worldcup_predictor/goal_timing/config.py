"""Configuration for Elite Goal Timing engine."""

from __future__ import annotations

GOAL_TIMING_MODEL_VERSION = "goal_timing_v0.3.1_phase51d_display"

# Phase 51D — first live predictions limited to leagues with sufficient local coverage.
GOAL_TIMING_PREDICTION_LEAGUE_KEYS: tuple[str, ...] = ("premier_league",)

GOAL_TIMING_MINUTE_RANGES: tuple[str, ...] = (
    "0-15",
    "16-30",
    "31-45+",
    "46-60",
    "61-75",
    "76-90+",
)

MIN_DATA_QUALITY_FOR_PREDICTION = 0.45

MINUTE_TOLERANCE_BANDS: tuple[tuple[str, int], ...] = (
    ("exact", 0),
    ("close", 5),
    ("acceptable", 10),
)

GOAL_TIMING_AGENT_KEYS: tuple[str, ...] = (
    "goal_timing_pattern",
    "first_goal_pressure",
    "lineup_goal_impact",
    "player_goal_threat",
    "tactical_goal_flow",
    "odds_goal_intelligence",
    "motivation_goal",
    "data_quality",
)

BACKTEST_DEFAULT_LOOKBACK_DAYS = 730
