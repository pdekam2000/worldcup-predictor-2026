"""Part B — failure attribution for incorrect predictions."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.root_cause.config import FAILURE_CATEGORIES
from worldcup_predictor.root_cause.models import FailureAttribution, MarketComparison


def _component_map(contributions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(c.get("component_id") or ""): c for c in contributions}


def _pick_matches(prediction: Any, reality: Any) -> bool | None:
    if prediction is None or reality is None:
        return None
    if isinstance(prediction, list):
        return str(reality) in [str(p) for p in prediction]
    return str(prediction).lower() == str(reality).lower()


def _odds_margin(contributions: list[dict[str, Any]], reality: Any) -> float | None:
    odds = _component_map(contributions).get("odds_intelligence")
    if not odds:
        return None
    conf = float(odds.get("confidence") or 0.5)
    pred = odds.get("prediction")
    if pred is None:
        return None
    if _pick_matches(pred, reality) is False:
        return round(1.0 - conf, 4)
    return round(conf - 0.5, 4)


def attribute_failure(
    comparison: MarketComparison,
    *,
    contributions: list[dict[str, Any]],
    fixture_meta: dict[str, Any] | None = None,
) -> FailureAttribution | None:
    if comparison.outcome != "incorrect":
        return None

    meta = fixture_meta or {}
    comps = _component_map(contributions)
    reasons: list[tuple[str, float, dict[str, Any]]] = []

    lineup = comps.get("lineup_intelligence")
    if lineup:
        pred = lineup.get("prediction")
        conf = float(lineup.get("confidence") or 0.5)
        if pred is not None and _pick_matches(pred, comparison.reality) is False:
            reasons.append(("lineup_mismatch", 0.72, {"lineup_prediction": pred}))
        elif pred is None or conf < 0.45:
            reasons.append(("missing_information", 0.65, {"signal": "low_lineup_confidence"}))

    odds = comps.get("odds_intelligence")
    gs = comps.get("goalscorer_intelligence")
    egie = comps.get("egie_historical_baseline")

    if odds and odds.get("prediction") is not None:
        odds_right = _pick_matches(odds.get("prediction"), comparison.reality) is True
        fusion_wrong = str(comparison.prediction).lower() != str(comparison.reality).lower()
        if odds_right and fusion_wrong:
            margin = _odds_margin(contributions, comparison.reality)
            if margin is not None and margin >= 0.15:
                reasons.append(("odds_disagreement", 0.78, {"odds_margin": margin}))
            else:
                reasons.append(("odds_disagreement", 0.62, {"odds_correct": True}))

    if gs and egie:
        gp, ep = gs.get("prediction"), egie.get("prediction")
        if gp is not None and ep is not None and str(gp) != str(ep):
            gs_hurt = _pick_matches(gp, comparison.reality) is False
            egie_hurt = _pick_matches(ep, comparison.reality) is False
            if gs_hurt or egie_hurt:
                reasons.append(("goalscorer_disagreement", 0.7, {"gs": gp, "egie": ep}))

    if egie and egie.get("prediction") is not None:
        if _pick_matches(egie.get("prediction"), comparison.reality) is False:
            reasons.append(("historical_prior_conflict", 0.68, {"egie_prediction": egie.get("prediction")}))

    dqs = meta.get("data_quality_score")
    if dqs is not None and float(dqs) < 0.55:
        reasons.append(("low_data_quality", 0.75, {"data_quality_score": float(dqs)}))

    hxg = meta.get("home_recent_xg")
    axg = meta.get("away_recent_xg")
    if hxg is None or axg is None or (float(hxg or 0) == 0 and float(axg or 0) == 0):
        reasons.append(("missing_information", 0.6, {"signal": "missing_xg"}))

    if comparison.tier in ("A", "B") and comparison.confidence >= 0.65:
        reasons.append(
            (
                "confidence_overestimation",
                0.8,
                {"tier": comparison.tier, "confidence": comparison.confidence},
            )
        )

    if meta.get("late_injury_flag"):
        reasons.append(("late_injury", 0.85, {"late_injury_flag": True}))

    if not reasons:
        reasons.append(("unknown", 0.35, {}))

    reasons.sort(key=lambda r: r[1], reverse=True)
    primary = reasons[0][0]
    if primary not in FAILURE_CATEGORIES:
        primary = "unknown"
    secondary = [r[0] for r in reasons[1:3] if r[0] in FAILURE_CATEGORIES]
    return FailureAttribution(
        fixture_id=comparison.fixture_id,
        market_id=comparison.market_id,
        failure_reason=primary,
        secondary_reasons=secondary,
        confidence=round(reasons[0][1], 4),
        evidence=reasons[0][2],
    )


def recommended_action_for(reason: str) -> str:
    actions = {
        "lineup_mismatch": "Increase lineup_intelligence weight gate; defer picks until T-60 lineup confidence rises",
        "late_injury": "Add injury freshness signal; reduce pre-match lock window",
        "odds_disagreement": "Review fusion weights when odds_intelligence disagrees with model stack by >15%",
        "low_data_quality": "Abstain or downgrade tier when data_quality_score < 0.55",
        "historical_prior_conflict": "Reduce egie_historical_baseline influence in high-variance tournaments",
        "goalscorer_disagreement": "Require goalscorer_intelligence alignment before FGT promotion",
        "confidence_overestimation": "Recalibrate hybrid_confidence_engine; cap Tier A at 0.75 until live validation",
        "missing_information": "Gate markets on xG + lineup availability",
        "unknown": "Collect more shadow evaluations; enrich component evidence payloads",
    }
    return actions.get(reason, actions["unknown"])
