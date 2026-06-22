"""Minute range helpers for goal timing features."""

from __future__ import annotations

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES

CUMULATIVE_MINUTE_THRESHOLDS: tuple[int, ...] = (15, 30, 45, 60, 75)


def effective_minute(minute: int | None, extra_minute: int | None = None) -> int | None:
    if minute is None:
        return None
    return int(minute) + int(extra_minute or 0)


def minute_to_range_key(minute: int | None) -> str | None:
    if minute is None:
        return None
    m = int(minute)
    if m <= 15:
        return "0-15"
    if m <= 30:
        return "16-30"
    if m <= 45:
        return "31-45+"
    if m <= 60:
        return "46-60"
    if m <= 75:
        return "61-75"
    return "76-90+"


def empty_range_counts() -> dict[str, int]:
    return {key: 0 for key in GOAL_TIMING_MINUTE_RANGES}


def counts_to_probabilities(counts: dict[str, int], *, alpha: float = 1.0) -> dict[str, float]:
    total = sum(counts.values())
    denom = total + alpha * len(counts)
    if denom <= 0:
        uniform = 1.0 / len(GOAL_TIMING_MINUTE_RANGES)
        return {k: round(uniform, 4) for k in GOAL_TIMING_MINUTE_RANGES}
    return {
        k: round((counts.get(k, 0) + alpha) / denom, 4)
        for k in GOAL_TIMING_MINUTE_RANGES
    }


def no_goal_before_minute_probs(goal_minutes: list[int]) -> dict[str, float]:
    """Probability no goal occurs before each cumulative threshold (match-level samples)."""
    if not goal_minutes:
        return {str(t): 1.0 for t in CUMULATIVE_MINUTE_THRESHOLDS}
    out: dict[str, float] = {}
    n = len(goal_minutes)
    for threshold in CUMULATIVE_MINUTE_THRESHOLDS:
        before = sum(1 for m in goal_minutes if m <= threshold)
        out[str(threshold)] = round(1.0 - (before / n), 4)
    return out
