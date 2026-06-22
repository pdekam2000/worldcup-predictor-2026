"""Display vs audit minute and confidence helpers for goal timing outputs."""

from __future__ import annotations

from worldcup_predictor.goal_timing.config import GOAL_TIMING_MINUTE_RANGES

DISPLAY_CONFIDENCE_DQ_THRESHOLD = 0.70
DISPLAY_CONFIDENCE_CAP_WHEN_DQ_LOW = 0.65

# Representative midpoint per bucket (display must stay inside bucket bounds).
BUCKET_REPRESENTATIVE_MINUTES: dict[str, float] = {
    "0-15": 8.0,
    "16-30": 23.0,
    "31-45+": 38.0,
    "46-60": 53.0,
    "61-75": 68.0,
    "76-90+": 83.0,
}

BUCKET_MINUTE_BOUNDS: dict[str, tuple[int, int]] = {
    "0-15": (0, 15),
    "16-30": (16, 30),
    "31-45+": (31, 45),
    "46-60": (46, 60),
    "61-75": (61, 75),
    "76-90+": (76, 90),
}


def weighted_average_minute(probs: dict[str, float]) -> float:
    total = sum(float(probs.get(k) or 0.0) for k in GOAL_TIMING_MINUTE_RANGES)
    if total <= 0:
        return 28.0
    minute = sum(
        float(probs.get(k) or 0.0) * BUCKET_REPRESENTATIVE_MINUTES[k]
        for k in GOAL_TIMING_MINUTE_RANGES
    ) / total
    return round(minute, 1)


def bucket_representative_minute(range_key: str) -> float:
    return float(BUCKET_REPRESENTATIVE_MINUTES.get(range_key, 28.0))


def clamp_minute_to_range(minute: float, range_key: str) -> float:
    bounds = BUCKET_MINUTE_BOUNDS.get(range_key)
    if not bounds:
        return round(minute, 1)
    lo, hi = bounds
    return round(max(lo, min(hi, float(minute))), 1)


def display_estimated_first_goal_minute(range_key: str) -> float:
    """Public display minute — always inside the selected first_goal_time_range bucket."""
    return clamp_minute_to_range(bucket_representative_minute(range_key), range_key)


def cap_display_confidence(model_confidence_score: float, data_quality_score: float) -> float:
    display = float(model_confidence_score)
    if float(data_quality_score) < DISPLAY_CONFIDENCE_DQ_THRESHOLD:
        display = min(display, DISPLAY_CONFIDENCE_CAP_WHEN_DQ_LOW)
    return round(display, 4)
