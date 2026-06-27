"""Phase A23 blueprint — minute_range vs expected_minute consistency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from worldcup_predictor.prediction.market_consistency_timing import (
    band_for_expected_minute,
    expected_minute_in_band,
    normalize_minute_band,
)

PredictionStatus = Literal["VALID", "INVALID"]
DataQualityLevel = Literal["HIGH", "MEDIUM", "LOW"]

DEVIATION_PENALTY_THRESHOLD_MINUTES = 15
DEVIATION_CONFIDENCE_PENALTY = 0.30


@dataclass(frozen=True)
class TimingConsistencyResult:
    prediction_status: PredictionStatus
    minute_range: str | None
    expected_minute: int | None
    expected_range: str | None
    deviation_minutes: int | None
    confidence_penalty: float
    reason: str


def _parse_expected_minute(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def validate_timing_consistency(
    *,
    minute_range: str | None,
    expected_minute: Any,
) -> TimingConsistencyResult:
    """
    A23 rules:
    - expected_minute outside minute_range → prediction_status=INVALID
    - deviation > 15 minutes from band midpoint → confidence_penalty=30%
    """
    band = normalize_minute_band(minute_range or "") if minute_range else None
    em = _parse_expected_minute(expected_minute)
    if band is None or em is None:
        return TimingConsistencyResult(
            prediction_status="VALID",
            minute_range=band,
            expected_minute=em,
            expected_range=band_for_expected_minute(em) if em is not None else None,
            deviation_minutes=None,
            confidence_penalty=0.0,
            reason="incomplete_timing_fields",
        )

    expected_range = band_for_expected_minute(em)
    in_band = expected_minute_in_band(em, band)
    if not in_band:
        return TimingConsistencyResult(
            prediction_status="INVALID",
            minute_range=band,
            expected_minute=em,
            expected_range=expected_range,
            deviation_minutes=_band_midpoint_distance(em, band),
            confidence_penalty=DEVIATION_CONFIDENCE_PENALTY,
            reason="expected_minute_outside_minute_range",
        )

    deviation = _band_midpoint_distance(em, band)
    penalty = DEVIATION_CONFIDENCE_PENALTY if deviation is not None and deviation > DEVIATION_PENALTY_THRESHOLD_MINUTES else 0.0
    return TimingConsistencyResult(
        prediction_status="VALID",
        minute_range=band,
        expected_minute=em,
        expected_range=expected_range,
        deviation_minutes=deviation,
        confidence_penalty=penalty,
        reason="aligned" if penalty == 0 else "high_deviation_within_band",
    )


def _band_midpoint_distance(minute: int, band: str) -> int | None:
    from worldcup_predictor.prediction.market_consistency_timing import parse_minute_band

    parsed = parse_minute_band(band)
    if parsed is None:
        return None
    start, end = parsed
    midpoint = (start + end) // 2
    return abs(int(minute) - midpoint)
