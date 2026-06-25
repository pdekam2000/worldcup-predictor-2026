"""Goal minute evaluation — Phase 46C-3."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcome
from worldcup_predictor.prediction.market_consistency_timing import (
    normalize_minute_band,
    parse_minute_band,
)

AdvancedStatus = Literal["correct", "wrong", "pending", "unavailable", "unknown", "void"]

EXACT_MINUTE_TOLERANCE = 5

_UNAVAILABLE_OUTCOME_TYPES = frozenset(
    {"POSTPONED", "CANCELLED", "CANC", "ABD", "ABANDONED", "SUSP", "SUSPENDED", "INT", "INTERRUPTED"}
)

_NO_GOAL_TOKENS = frozenset({"no_goal", "no goal", "none", "0-0", "nil", "no scorer"})


def _parse_scoreline(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    text = str(value).strip().replace(":", "-")
    if "-" not in text:
        return None, None
    left, _, right = text.partition("-")
    try:
        return int(left.strip()), int(right.strip())
    except ValueError:
        return None, None


def _match_outcome_unavailable(outcome: FixtureOutcome) -> bool:
    mot = str(outcome.match_outcome_type or "").upper()
    if mot in _UNAVAILABLE_OUTCOME_TYPES:
        return True
    status = str(outcome.fixture_status or "").upper()
    return status in _UNAVAILABLE_OUTCOME_TYPES


def _market_result(
    *,
    market: str,
    predicted: str | None,
    actual: str | None,
    status: AdvancedStatus,
    confidence: float | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "market": market,
        "predicted": predicted,
        "actual": actual,
        "status": status,
        "confidence": confidence,
        "reason": reason,
    }


@dataclass(frozen=True)
class GoalMinutePrediction:
    kind: Literal["band", "exact", "no_goal"]
    display: str
    band: str | None = None
    exact_minute: int | None = None
    confidence: float | None = None


def _normalize_band_label(band: str) -> str:
    text = normalize_minute_band(band)
    if text == "1-15":
        return "0-15"
    if text == "90+":
        return "76-90+"
    return text


def _parse_exact_minute(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text or text.lower() in _NO_GOAL_TOKENS:
        return None
    if re.fullmatch(r"\d{1,3}", text):
        return int(text)
    return None


def parse_goal_minute_prediction(payload: dict[str, Any]) -> GoalMinutePrediction | None:
    dm = payload.get("detailed_markets") or {}
    fg = dm.get("first_goal") if isinstance(dm, dict) else None
    if not isinstance(fg, dict):
        return None

    minute_range = str(fg.get("minute_range") or "").strip()
    expected = fg.get("expected_minute")
    conf_raw = fg.get("confidence")
    try:
        confidence = float(conf_raw) if conf_raw is not None else None
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None and confidence > 1:
        confidence = confidence / 100.0

    if minute_range.lower() in _NO_GOAL_TOKENS:
        return GoalMinutePrediction(kind="no_goal", display="no_goal", confidence=confidence)

    band_label = _normalize_band_label(minute_range) if minute_range else ""
    if band_label and parse_minute_band(band_label):
        return GoalMinutePrediction(
            kind="band",
            display=band_label,
            band=band_label,
            confidence=confidence,
        )

    exact = _parse_exact_minute(expected)
    if exact is not None:
        return GoalMinutePrediction(
            kind="exact",
            display=str(exact),
            exact_minute=exact,
            confidence=confidence,
        )

    exact_from_range = _parse_exact_minute(minute_range)
    if exact_from_range is not None:
        return GoalMinutePrediction(
            kind="exact",
            display=str(exact_from_range),
            exact_minute=exact_from_range,
            confidence=confidence,
        )

    return None


def effective_goal_minute(minute: int | None, extra_minute: int | None = None) -> int | None:
    """Normalize stoppage/extra time for evaluation."""
    if minute is None:
        return None
    m = int(minute)
    extra = int(extra_minute) if extra_minute else 0
    if m == 45 and extra > 0:
        return 45
    if m >= 90:
        return 90
    return m


def resolve_actual_first_goal_minute(outcome: FixtureOutcome) -> tuple[int | None, int | None, str | None]:
    """Return (raw_minute, effective_minute, display_text)."""
    minute = outcome.first_goal_minute
    extra = outcome.first_goal_extra_minute

    if minute is None and outcome.goal_events:
        first = outcome.goal_events[0]
        if isinstance(first, dict):
            minute = first.get("minute")
            extra = first.get("extra_minute")

    if minute is None:
        return None, None, None

    raw = int(minute)
    extra_i = int(extra) if extra is not None else 0
    effective = effective_goal_minute(raw, extra_i)
    if extra_i > 0 and raw in {45, 90}:
        display = f"{raw}+{extra_i} (eval={effective})"
    else:
        display = str(effective if effective is not None else raw)
    return raw, effective, display


def minute_in_band(actual: int, band: str) -> bool:
    label = _normalize_band_label(band)
    parsed = parse_minute_band(label)
    if parsed is None:
        return False
    start, end = parsed
    if label in {"76-90+", "76-90"}:
        return actual >= start
    return start <= actual <= end


def evaluate_goal_minute_band(actual: int, band: str) -> bool:
    return minute_in_band(actual, band)


def evaluate_goal_minute_exact(actual: int, predicted: int, *, tolerance: int = EXACT_MINUTE_TOLERANCE) -> bool:
    return abs(actual - predicted) <= tolerance


def evaluate_goal_minute(payload: dict[str, Any], outcome: FixtureOutcome) -> dict[str, Any]:
    market = "goal_minute"
    if not outcome.is_finished:
        return _market_result(
            market=market,
            predicted=None,
            actual=None,
            status="pending",
            reason="match_not_finished",
        )
    if _match_outcome_unavailable(outcome):
        return _market_result(
            market=market,
            predicted=None,
            actual=None,
            status="unavailable",
            reason=f"match_outcome_type={outcome.match_outcome_type or outcome.fixture_status}",
        )

    prediction = parse_goal_minute_prediction(payload)
    home, away = _parse_scoreline(outcome.final_score)
    no_goals = home == 0 and away == 0 if home is not None and away is not None else False

    if no_goals:
        if prediction and prediction.kind == "no_goal":
            return _market_result(
                market=market,
                predicted="no_goal",
                actual="no_goal",
                status="correct",
                confidence=prediction.confidence,
                reason="zero_zero_no_goal",
            )
        return _market_result(
            market=market,
            predicted=prediction.display if prediction else None,
            actual="no_goal",
            status="unavailable",
            confidence=prediction.confidence if prediction else None,
            reason="zero_zero_no_goal",
        )

    raw_minute, effective, display = resolve_actual_first_goal_minute(outcome)
    if effective is None:
        return _market_result(
            market=market,
            predicted=prediction.display if prediction else None,
            actual=None,
            status="unavailable",
            confidence=prediction.confidence if prediction else None,
            reason="first_goal_minute_missing",
        )

    if not prediction:
        return _market_result(
            market=market,
            predicted=None,
            actual=display,
            status="unavailable",
            reason="no_goal_minute_prediction",
        )

    if prediction.kind == "no_goal":
        return _market_result(
            market=market,
            predicted="no_goal",
            actual=display,
            status="wrong",
            confidence=prediction.confidence,
            reason="goal_scored",
        )

    if prediction.kind == "band":
        band = prediction.band or prediction.display
        in_band = evaluate_goal_minute_band(effective, band)
        stoppage_note = None
        if raw_minute is not None and raw_minute != effective:
            stoppage_note = f"stoppage_normalized:{raw_minute}->{effective}"
        return _market_result(
            market=market,
            predicted=band,
            actual=display,
            status="correct" if in_band else "wrong",
            confidence=prediction.confidence,
            reason=stoppage_note,
        )

    predicted_exact = prediction.exact_minute
    if predicted_exact is None:
        return _market_result(
            market=market,
            predicted=prediction.display,
            actual=display,
            status="unavailable",
            confidence=prediction.confidence,
            reason="invalid_exact_prediction",
        )

    within = evaluate_goal_minute_exact(effective, predicted_exact)
    reason = f"exact_tolerance_pm{EXACT_MINUTE_TOLERANCE}"
    if raw_minute is not None and raw_minute != effective:
        reason = f"stoppage_normalized:{raw_minute}->{effective};{reason}"
    return _market_result(
        market=market,
        predicted=str(predicted_exact),
        actual=display,
        status="correct" if within else "wrong",
        confidence=prediction.confidence,
        reason=reason,
    )
