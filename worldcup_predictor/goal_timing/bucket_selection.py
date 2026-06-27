"""Goal timing bucket selection — avoid false 0-15 defaults on ties."""

from __future__ import annotations

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES
from worldcup_predictor.goal_timing.minute_display import weighted_average_minute
from worldcup_predictor.goal_timing.minute_ranges import minute_to_range_key


def _is_uniform(dist: dict[str, float], *, tolerance: float = 0.02) -> bool:
    if not dist:
        return True
    vals = [float(dist.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES]
    if not vals or max(vals) <= 0:
        return True
    uniform = 1.0 / len(GOAL_TIMING_MINUTE_RANGES)
    return max(abs(v - uniform) for v in vals) <= tolerance


def pick_goal_time_range(
    match_range_probs: dict[str, float],
) -> tuple[str | None, bool, str]:
    """
    Pick displayed goal-time range from model probabilities.

    Returns (range_key, bucket_is_default, bucket_reason).
    """
    if not match_range_probs:
        return None, True, "missing_range_probabilities"

    probs = {k: float(match_range_probs.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES}
    total = sum(probs.values())
    if total <= 0 or _is_uniform(probs):
        wavg = weighted_average_minute(probs if total > 0 else {k: 1.0 for k in GOAL_TIMING_MINUTE_RANGES})
        picked = minute_to_range_key(int(round(wavg)))
        return picked, True, "uniform_prior_weighted_average"

    max_prob = max(probs.values())
    leaders = [k for k in GOAL_TIMING_MINUTE_RANGES if probs.get(k, 0.0) >= max_prob - 1e-9]
    if len(leaders) > 1:
        wavg = weighted_average_minute(probs)
        picked = minute_to_range_key(int(round(wavg)))
        return picked, True, "tie_break_weighted_average"

    return leaders[0], False, "model_output"
