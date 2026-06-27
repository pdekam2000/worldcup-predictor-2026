"""Phase A23 — lifecycle states, colors, market keys."""

from __future__ import annotations

from typing import Literal

LifecycleState = Literal[
    "generated",
    "updated",
    "kickoff",
    "live",
    "finished",
    "evaluated",
    "archived",
]

LIFECYCLE_STATES: tuple[str, ...] = (
    "generated",
    "updated",
    "kickoff",
    "live",
    "finished",
    "evaluated",
    "archived",
)

RESULT_COLORS: dict[str, str] = {
    "correct": "green",
    "wrong": "red",
    "pending": "yellow",
    "void": "gray",
    "push": "gray",
    "unknown": "gray",
    "unavailable": "gray",
    "partial": "yellow",
}

TIER_COLORS: dict[str, str] = {
    "elite": "gold",
    "official": "green",
    "value": "purple",
    "caution": "yellow",
}

MARKET_WINDOWS: tuple[str, ...] = ("7d", "30d", "90d", "all")

TRACKED_MARKETS: tuple[str, ...] = (
    "1x2",
    "over_under_2_5",
    "btts",
    "double_chance",
    "correct_score",
    "first_goal_team",
    "goal_timing",
    "goalscorer",
    "halftime",
)
