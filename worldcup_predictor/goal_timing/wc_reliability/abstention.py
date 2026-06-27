"""Phase A23 blueprint — official abstention (BET / LEAN / PASS)."""

from __future__ import annotations

from typing import Literal

DataQualityLevel = Literal["HIGH", "MEDIUM", "LOW"]
PredictionAction = Literal["BET", "LEAN", "PASS"]

PASS_REASONS = frozenset(
    {
        "timing_conflict",
        "missing_egie",
        "missing_range_probabilities",
        "model_disagreement",
        "low_data_quality",
        "bucket_probabilities_too_close",
        "high_timing_deviation",
    }
)


def decide_prediction_action(
    *,
    data_quality: DataQualityLevel,
    no_clear_edge: bool,
    timing_invalid: bool,
    reasons: list[str],
    model_disagreement: bool = False,
) -> PredictionAction:
    """
    PASS if any hard abstention condition.
    BET only on HIGH quality, clear edge, valid timing.
    LEAN otherwise when some signal exists.
    """
    reason_set = set(reasons)
    if model_disagreement:
        reason_set.add("model_disagreement")

    if timing_invalid or "timing_conflict" in reason_set:
        return "PASS"
    if data_quality == "LOW":
        return "PASS"
    if "missing_egie" in reason_set and data_quality != "HIGH":
        return "PASS"
    if "missing_range_probabilities" in reason_set:
        return "PASS"
    if no_clear_edge:
        return "PASS"
    if model_disagreement:
        return "PASS"

    if data_quality == "HIGH" and not no_clear_edge:
        return "BET"
    if data_quality == "MEDIUM":
        return "LEAN"
    return "PASS"
