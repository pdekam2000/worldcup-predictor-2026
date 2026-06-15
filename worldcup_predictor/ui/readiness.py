"""Readiness labels and human-readable reasons for match analysis."""

from __future__ import annotations

from typing import Any, Literal

from worldcup_predictor.domain.prediction import MatchPrediction

ReadinessLabel = Literal[
    "Strong Ready",
    "Good Analysis",
    "Moderate Analysis",
    "Low Confidence",
    "Not Ready",
]


def _data_quality_pct(prediction: MatchPrediction | None) -> float:
    if prediction is None or prediction.confidence_breakdown is None:
        return 0.0
    return float(prediction.confidence_breakdown.data_quality_score) * 100.0


def _prediction_quality(prediction: MatchPrediction | None) -> float:
    if prediction is None:
        return 0.0
    return float(getattr(prediction, "prediction_quality_score", 0.0) or 0.0)


def build_readiness_reason(
    prediction: MatchPrediction | None,
    *,
    intel: Any | None = None,
    placeholder: bool = False,
    api_configured: bool = True,
) -> str:
    missing: list[str] = []
    available: list[str] = []

    if intel is not None:
        for item in getattr(intel, "missing_data", None) or []:
            label = str(item).replace("_", " ")
            if "lineup" in label.lower():
                missing.append("official lineups")
            elif "injur" in label.lower():
                missing.append("injury reports")
            elif "odds" in label.lower():
                missing.append("live odds")
            else:
                missing.append(label)
        if getattr(intel, "odds", None) and intel.odds.available:
            available.append("odds")
        if getattr(intel, "home_team", None) and getattr(intel.home_team, "form", None):
            available.append("form")
        if getattr(intel, "home_team", None) and getattr(intel.home_team, "statistics", None):
            available.append("team stats")

    if prediction is not None:
        if prediction.lineup_warning:
            missing.append("confirmed lineups")
        if prediction.missing_data_warnings:
            pass
        if _data_quality_pct(prediction) >= 45:
            available.append("data quality")

    if placeholder or not api_configured:
        return "Fixture data unavailable or API not configured."

    if missing and available:
        miss = ", ".join(dict.fromkeys(missing))
        avail = ", ".join(dict.fromkeys(available))
        return f"Missing {miss}, but {avail} are available."
    if missing:
        return f"Missing {', '.join(dict.fromkeys(missing))}."
    if available:
        return f"{', '.join(dict.fromkeys(available)).capitalize()} loaded — review confidence before relying on output."
    return "Core fixture data loaded."


def analysis_readiness(
    prediction: MatchPrediction | None,
    *,
    placeholder: bool = False,
    api_configured: bool = False,
    intel: Any | None = None,
) -> tuple[ReadinessLabel, float, str]:
    """Return readiness label, progress 0–1, and explanatory reason."""
    dq_pct = _data_quality_pct(prediction)
    pq = _prediction_quality(prediction)
    reason = build_readiness_reason(
        prediction,
        intel=intel,
        placeholder=placeholder,
        api_configured=api_configured,
    )

    if prediction is None:
        if placeholder or not api_configured:
            return "Not Ready", 0.2, reason
        return "Moderate Analysis", 0.45, "Run prediction for a full readiness score."

    if dq_pct < 30 or pq < 30:
        return "Not Ready", min(max(dq_pct / 100.0, 0.15), 0.35), reason

    score = float(prediction.confidence_score)
    progress = min(max(score / 100.0, 0.0), 1.0)

    if score >= 75 and dq_pct >= 55:
        return "Strong Ready", progress, reason
    if score >= 60 and dq_pct >= 45:
        return "Good Analysis", progress, reason
    if score >= 45:
        return "Moderate Analysis", progress, reason
    return "Low Confidence", progress, reason
