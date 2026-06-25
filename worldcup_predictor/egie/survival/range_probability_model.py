"""Range probability model from blended survival curves."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.survival.config import (
    AWAY_PROFILE_RANGE_WEIGHT,
    HOME_PROFILE_RANGE_WEIGHT,
    LEAGUE_RANGE_WEIGHT,
)
from worldcup_predictor.egie.survival.hazard_model import bucket_goal_probabilities
from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.minute_ranges import counts_to_probabilities


def _normalize(dist: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(dist.get(k) or 0.0)) for k in GOAL_TIMING_MINUTE_RANGES)
    if total <= 0:
        uniform = round(1.0 / len(GOAL_TIMING_MINUTE_RANGES), 4)
        return {k: uniform for k in GOAL_TIMING_MINUTE_RANGES}
    return {k: round(max(0.0, float(dist.get(k) or 0.0)) / total, 4) for k in GOAL_TIMING_MINUTE_RANGES}


def _blend(
    league: dict[str, float],
    home: dict[str, float],
    away: dict[str, float],
    *,
    league_w: float = LEAGUE_RANGE_WEIGHT,
    home_w: float = HOME_PROFILE_RANGE_WEIGHT,
    away_w: float = AWAY_PROFILE_RANGE_WEIGHT,
) -> dict[str, float]:
    out = {k: 0.0 for k in GOAL_TIMING_MINUTE_RANGES}
    weight_sum = league_w + home_w + away_w
    for bucket in GOAL_TIMING_MINUTE_RANGES:
        out[bucket] = (
            league_w * float(league.get(bucket) or 0.0)
            + home_w * float(home.get(bucket) or 0.0)
            + away_w * float(away.get(bucket) or 0.0)
        ) / weight_sum
    return _normalize(out)


def range_probabilities_from_profiles(
    *,
    league_survival_curve: list[dict[str, float]],
    home_profile: dict[str, Any] | None,
    away_profile: dict[str, Any] | None,
) -> dict[str, float]:
    """Full bucket probability distribution for a fixture."""
    league_probs = bucket_goal_probabilities(league_survival_curve)
    home_probs = (home_profile or {}).get("goal_timing_distribution") or league_probs
    away_probs = (away_profile or {}).get("goal_timing_distribution") or league_probs
    return _blend(league_probs, home_probs, away_probs)


def pick_primary_range(range_probs: dict[str, float]) -> str:
    return max(GOAL_TIMING_MINUTE_RANGES, key=lambda k: float(range_probs.get(k) or 0.0))


def expected_minute_from_ranges(range_probs: dict[str, float]) -> float:
    """Weighted average minute using bucket midpoints."""
    from worldcup_predictor.goal_timing.minute_display import BUCKET_REPRESENTATIVE_MINUTES

    total = sum(float(range_probs.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES)
    if total <= 0:
        return 28.0
    minute = sum(
        float(range_probs.get(k) or 0.0) * BUCKET_REPRESENTATIVE_MINUTES[k]
        for k in GOAL_TIMING_MINUTE_RANGES
    ) / total
    return round(minute, 1)


def legacy_counts_fallback(counts: dict[str, int]) -> dict[str, float]:
    return counts_to_probabilities(counts)
