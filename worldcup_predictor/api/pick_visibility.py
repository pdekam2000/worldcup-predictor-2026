"""Phase 33B — user-visible pick tiers (official vs caution) without hiding predictions."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.prediction import MatchPrediction

OFFICIAL_CONFIDENCE_THRESHOLD = 60.0

CAUTION_MESSAGE = (
    "Confidence is below premium threshold, but this is the strongest available market."
)


def _gap_to_threshold(confidence: float) -> float:
    return round(max(0.0, OFFICIAL_CONFIDENCE_THRESHOLD - confidence), 1)


def _caution_reason(prediction: MatchPrediction, confidence: float, data_quality: float) -> str:
    parts: list[str] = []
    if prediction.no_bet_flag:
        parts.append("WDE flagged elevated uncertainty")
    if confidence < OFFICIAL_CONFIDENCE_THRESHOLD:
        parts.append(f"confidence {confidence:.1f} below {OFFICIAL_CONFIDENCE_THRESHOLD:.0f}")
    if data_quality < 45.0:
        parts.append(f"data quality {data_quality:.1f} below 45")
    return "; ".join(parts) if parts else "below official recommendation threshold"


def _pick_display(pick: dict[str, Any] | None, *, prefix: str) -> dict[str, Any] | None:
    if not pick:
        return None
    out = dict(pick)
    out["display_text"] = f"{prefix}: {pick.get('pick') or pick.get('market')}"
    out["status"] = "caution"
    out["pick_tier"] = "caution"
    return out


def enrich_pick_visibility(
    block: dict[str, Any],
    prediction: MatchPrediction,
    *,
    data_quality: float | None = None,
) -> dict[str, Any]:
    """Add 33B user-facing fields; keep internal no_bet from WDE."""
    out = dict(block)
    confidence = float(prediction.confidence_score or 0.0)
    dq = data_quality if data_quality is not None else float(out.get("data_quality") or 0.0)
    internal_no_bet = bool(
        prediction.no_bet_flag
        or confidence < OFFICIAL_CONFIDENCE_THRESHOLD
        or dq < 45.0
    )

    out["no_bet"] = internal_no_bet
    official = not internal_no_bet
    out["pick_tier"] = "official" if official else "caution"
    out["confidence_gap_to_threshold"] = _gap_to_threshold(confidence) if not official else 0.0
    out["caution_reason"] = None if official else _caution_reason(prediction, confidence, dq)

    caution_pick = out.get("caution_pick")
    best_available = out.get("best_available_pick")

    if official:
        user_visible = out.get("safe_pick") or out.get("value_pick") or out.get("aggressive_pick")
        out["user_visible_pick"] = user_visible
        tracking = dict(out.get("accuracy_tracking") or {})
        tracking["official_recommended"] = True
        tracking["caution_pick"] = None
        tracking["no_bet"] = internal_no_bet
        out["accuracy_tracking"] = tracking
        return out

    risk = "high" if confidence < 50 else "medium"
    out["risk_level"] = risk

    if not caution_pick and out.get("market_ranking"):
        top = out["market_ranking"][0] if out["market_ranking"] else None
        if top:
            caution_pick = dict(top)
            caution_pick["bucket"] = "CAUTION"
    if not best_available and len(out.get("market_ranking") or []) > 1:
        best_available = dict(out["market_ranking"][1])
        best_available["bucket"] = "BEST_AVAILABLE"

    out["caution_pick"] = _pick_display(caution_pick, prefix="Low Confidence Pick") if caution_pick else None
    out["best_available_pick"] = _pick_display(best_available, prefix="Best Available Pick") if best_available else out.get("caution_pick")
    out["user_visible_pick"] = out.get("caution_pick") or out.get("best_available_pick")

    recs: list[dict[str, Any]] = []
    for key, pick, label in (
        ("caution_pick", out.get("caution_pick"), "Low Confidence Pick"),
        ("best_available_pick", out.get("best_available_pick"), "Best Available Pick"),
    ):
        if not pick:
            continue
        recs.append({
            "market": pick.get("market"),
            "market_key": pick.get("market_key"),
            "pick": pick.get("pick"),
            "selection": pick.get("selection"),
            "display_text": pick.get("display_text") or f"{label}: {pick.get('pick')}",
            "confidence": pick.get("confidence") or round(confidence / 100.0, 3),
            "risk_level": risk,
            "reasoning": CAUTION_MESSAGE,
            "source_agents": pick.get("source_agents") or ["WDE"],
            "status": "caution",
            "pick_tier": "caution",
            "bucket": pick.get("bucket"),
        })

    if recs:
        out["recommended_bets"] = recs
        out["primary_recommendation"] = recs[0]

    tracking = dict(out.get("accuracy_tracking") or {})
    tracking["official_recommended"] = False
    tracking["caution_pick"] = {
        "market_key": (out.get("caution_pick") or {}).get("market_key"),
        "selection": (out.get("caution_pick") or {}).get("selection"),
        "pick": (out.get("caution_pick") or {}).get("pick"),
    } if out.get("caution_pick") else None
    tracking["best_available_pick"] = {
        "market_key": (out.get("best_available_pick") or {}).get("market_key"),
        "selection": (out.get("best_available_pick") or {}).get("selection"),
        "pick": (out.get("best_available_pick") or {}).get("pick"),
    } if out.get("best_available_pick") else None
    tracking["no_bet"] = internal_no_bet
    out["accuracy_tracking"] = tracking
    return out
