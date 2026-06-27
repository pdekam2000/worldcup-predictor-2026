"""Unified confidence and tier system — Phase 61."""

from __future__ import annotations

from typing import Any


def _norm_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        c = float(value)
    except (TypeError, ValueError):
        return None
    if c <= 1.0:
        c *= 100.0
    return max(0.0, min(100.0, c))


def confidence_to_tier(confidence: float | None) -> str:
    c = _norm_confidence(confidence)
    if c is None:
        return "D"
    if c >= 80:
        return "A"
    if c >= 60:
        return "B"
    if c >= 40:
        return "C"
    return "D"


def risk_from_tier(tier: str, *, disagreement: bool = False) -> str:
    base = {
        "A": "moderate",
        "B": "moderate",
        "C": "elevated",
        "D": "high",
    }.get(tier, "high")
    if disagreement and base == "moderate":
        return "elevated"
    if disagreement:
        return "high"
    return base


def compute_unified_confidence(
    *,
    base_confidence: float | None,
    data_quality: float | None,
    engine_agreement: str = "agree",
    historical_accuracy: float | None = None,
    sample_size: int | None = None,
    odds_agreement: bool | None = None,
) -> float | None:
    c = _norm_confidence(base_confidence)
    if c is None:
        return None

    dq = float(data_quality) if data_quality is not None else 0.65
    score = c * 0.55 + dq * 100.0 * 0.20

    if historical_accuracy is not None:
        score += float(historical_accuracy) * 100.0 * 0.15
    else:
        score += 50.0 * 0.15

    if sample_size is not None and sample_size < 20:
        score *= 0.92

    if engine_agreement == "disagree":
        score *= 0.85
    elif engine_agreement == "partial":
        score *= 0.92

    if odds_agreement is False:
        score *= 0.9
    elif odds_agreement is True:
        score *= 1.03

    return round(max(0.0, min(100.0, score)), 1)


def build_confidence_explanation(factors: dict[str, Any]) -> str:
    parts: list[str] = []
    if factors.get("engine_agreement") == "disagree":
        parts.append("Classic and EGIE disagree on this market — confidence reduced.")
    elif factors.get("engine_agreement") == "partial":
        parts.append("Partial agreement between engines.")
    if factors.get("data_quality", 1) < 0.5:
        parts.append("Limited provider data available.")
    if factors.get("odds_agreement") is False:
        parts.append("Odds market leans a different direction.")
    if not parts:
        parts.append("Models and provider data are broadly aligned.")
    return " ".join(parts)
