"""Discrete hazard curve derived from Kaplan–Meier survival."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.survival.config import RANGE_BUCKET_BOUNDS
from worldcup_predictor.egie.survival.kaplan_meier import survival_at
from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES


def hazard_curve_from_km(survival_curve: list[dict[str, float]]) -> dict[str, Any]:
    """
    Instantaneous discrete hazard per EGIE minute bucket.

    h(bucket) ≈ P(goal in bucket | survived to bucket start)
    """
    hazards: dict[str, float] = {}
    peak_bucket = GOAL_TIMING_MINUTE_RANGES[0]
    peak_hazard = 0.0

    for bucket in GOAL_TIMING_MINUTE_RANGES:
        lo, hi = RANGE_BUCKET_BOUNDS[bucket]
        s_before = survival_at(survival_curve, float(lo - 1) if lo > 0 else 0.0)
        s_after = survival_at(survival_curve, float(hi))
        if s_before <= 0:
            h = 0.0
        else:
            h = max(0.0, (s_before - s_after) / s_before)
        hazards[bucket] = round(h, 6)
        if h > peak_hazard:
            peak_hazard = h
            peak_bucket = bucket

    return {
        "hazard_by_bucket": hazards,
        "peak_bucket": peak_bucket,
        "peak_hazard": round(peak_hazard, 6),
    }


def bucket_goal_probabilities(survival_curve: list[dict[str, float]]) -> dict[str, float]:
    """P(first goal in each bucket) from KM survival."""
    probs: dict[str, float] = {}
    for bucket in GOAL_TIMING_MINUTE_RANGES:
        lo, hi = RANGE_BUCKET_BOUNDS[bucket]
        s_before = survival_at(survival_curve, float(lo - 1) if lo > 0 else 0.0)
        s_after = survival_at(survival_curve, float(hi))
        probs[bucket] = max(0.0, s_before - s_after)
    total = sum(probs.values()) or 1.0
    return {k: round(v / total, 4) for k, v in probs.items()}
