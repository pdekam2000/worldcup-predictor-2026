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


def _attach_no_bet_diagnostics(out: dict[str, Any], prediction: MatchPrediction) -> None:
    """Additive owner/research diagnostics from post-enrichment recompute (if present)."""
    md = prediction.metadata or {}
    if md.get("no_bet_recomputed") != "true":
        return
    reasons_raw = md.get("no_bet_reasons") or ""
    reasons = [r for r in str(reasons_raw).split(",") if r]
    out["no_bet_recomputed"] = True
    out["no_bet_decision_stage"] = md.get("no_bet_decision_stage") or "FINAL_POST_ENRICHMENT"
    out["no_bet_reasons"] = reasons
    out["no_bet_cleared_reasons"] = [
        r for r in str(md.get("no_bet_cleared_reasons") or "").split(",") if r
    ]
    out["no_bet_retained_reasons"] = [
        r for r in str(md.get("no_bet_retained_reasons") or "").split(",") if r
    ]
    if md.get("baseline_no_bet") is not None:
        out["baseline_no_bet"] = str(md.get("baseline_no_bet")).lower() == "true"
    if md.get("final_no_bet") is not None:
        out["final_no_bet"] = str(md.get("final_no_bet")).lower() == "true"
    details_json = md.get("no_bet_reason_details_json")
    if details_json:
        try:
            import json

            out["no_bet_reason_details"] = json.loads(details_json)
        except Exception:
            pass
    if md.get("no_bet_recompute_mode") == "shadow" and md.get("shadow_final_no_bet") is not None:
        out["shadow_final_no_bet"] = str(md.get("shadow_final_no_bet")).lower() == "true"


def _ensure_no_bet_reasons_invariant(
    out: dict[str, Any],
    prediction: MatchPrediction,
    *,
    confidence: float,
    data_quality: float,
    internal_no_bet: bool,
) -> None:
    """Invariant: no_bet=true ⇒ non-empty reasons aligned to current gates.

    Does not add new no_bet *conditions* — only serializes reasons for gates already
    applied by evaluator and/or this visibility layer (conf < 60, dq < 45).
    """
    if not internal_no_bet:
        # Active reasons must be empty when betting is allowed.
        if not out.get("no_bet_reasons"):
            out["no_bet_reasons"] = []
        return

    reasons = [str(r) for r in (out.get("no_bet_reasons") or []) if r]
    if reasons:
        out["no_bet_reasons"] = reasons
        return

    from worldcup_predictor.decision.no_bet_evaluator import evaluate_no_bet_reasons
    from worldcup_predictor.decision.no_bet_reasons import NoBetReason

    decision = evaluate_no_bet_reasons(
        confidence=confidence,
        wde_data_quality=data_quality,
        visibility_data_quality=data_quality,
        scoring_data_quality=data_quality,
        placeholder=bool(getattr(prediction, "is_placeholder", False)),
    )
    reasons = list(decision.active_reasons)
    # Mirror visibility gates already enforced above when recompute left reasons empty.
    if confidence < OFFICIAL_CONFIDENCE_THRESHOLD and NoBetReason.CONFIDENCE_BELOW_60.value not in reasons:
        reasons.append(NoBetReason.CONFIDENCE_BELOW_60.value)
    if data_quality < 45.0 and NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45.value not in reasons:
        reasons.append(NoBetReason.VISIBILITY_DATA_QUALITY_BELOW_45.value)
    if not reasons:
        reasons = [NoBetReason.CONFIDENCE_BELOW_60.value]
    out["no_bet_reasons"] = reasons
    out["no_bet_reasons_repaired"] = True
    out["no_bet_decision_stage"] = out.get("no_bet_decision_stage") or "PICK_VISIBILITY_INVARIANT"


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
    md = prediction.metadata or {}
    recompute_active = (
        md.get("no_bet_recomputed") == "true"
        and md.get("no_bet_recompute_mode") == "active"
    )
    if recompute_active:
        # Consume final recomputed decision — do NOT re-OR sticky inherited flag alone.
        # Defense-in-depth: visibility thresholds remain enforced.
        internal_no_bet = bool(prediction.no_bet_flag)
        if confidence < OFFICIAL_CONFIDENCE_THRESHOLD or dq < 45.0:
            internal_no_bet = True
    else:
        internal_no_bet = bool(
            prediction.no_bet_flag
            or confidence < OFFICIAL_CONFIDENCE_THRESHOLD
            or dq < 45.0
        )

    out["no_bet"] = internal_no_bet
    _attach_no_bet_diagnostics(out, prediction)
    _ensure_no_bet_reasons_invariant(
        out, prediction, confidence=confidence, data_quality=dq, internal_no_bet=internal_no_bet
    )
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
