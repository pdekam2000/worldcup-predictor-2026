"""PredOps constants — Phase A15."""

from __future__ import annotations

COVERAGE_STATES = frozenset(
    {
        "missing",
        "queued",
        "generating",
        "completed",
        "stale",
        "failed",
        "no_bet",
        "unavailable",
    }
)

MARKET_STATUS_PREDICTION = "prediction"
MARKET_STATUS_NO_PICK = "no_pick"
MARKET_STATUS_UNAVAILABLE = "unavailable"

CORE_MARKET_IDS: tuple[str, ...] = (
    "1x2",
    "double_chance",
    "btts",
    "over_under_0_5",
    "over_under_1_5",
    "over_under_2_5",
    "over_under_3_5",
    "correct_score",
    "ht_result",
    "ht_ft",
)

EGIE_MARKET_IDS: tuple[str, ...] = (
    "first_goal_team",
    "first_goal_time_range",
    "estimated_first_goal_minute",
    "next_goal_team",
    "team_goals_home",
    "team_goals_away",
    "goal_timing_confidence",
    "goal_timing_tier",
)

PLAYER_MARKET_IDS: tuple[str, ...] = (
    "anytime_goalscorer",
    "first_goalscorer",
    "player_most_likely_to_score",
)

ALL_MARKET_IDS: tuple[str, ...] = CORE_MARKET_IDS + EGIE_MARKET_IDS + PLAYER_MARKET_IDS

QUEUE_STATUS_QUEUED = "queued"
QUEUE_STATUS_GENERATING = "generating"
QUEUE_STATUS_COMPLETED = "completed"
QUEUE_STATUS_FAILED = "failed"
