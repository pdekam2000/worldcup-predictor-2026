"""Hybrid decision layer — market-weighted fusion without modifying source engines."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.unified_hybrid.confidence import (
    build_confidence_explanation,
    compute_unified_confidence,
    confidence_to_tier,
    risk_from_tier,
)
from worldcup_predictor.unified_hybrid.models import UnifiedMarketPick

MARKET_LABELS = {
    "1x2": "1X2",
    "btts": "BTTS",
    "over_under_2_5": "Over/Under 2.5",
    "double_chance": "Double Chance",
    "correct_score": "Correct Score",
    "ht_result": "Half Time Result",
    "first_goal_team": "First Goal Team",
    "first_goal_time_range": "First Goal Time Range",
    "estimated_first_goal_minute": "Approx First Goal Minute",
    "anytime_goalscorer": "Anytime Goalscorer",
    "first_goalscorer": "First Goalscorer",
}

# Classic weight, EGIE weight for goal markets
_FUSION_WEIGHTS: dict[str, tuple[float, float]] = {
    "1x2": (0.70, 0.0),
    "btts": (0.75, 0.0),
    "over_under_2_5": (0.70, 0.0),
    "double_chance": (0.80, 0.0),
    "correct_score": (0.85, 0.0),
    "ht_result": (0.75, 0.0),
    "first_goal_team": (0.25, 0.75),
    "first_goal_time_range": (0.10, 0.90),
    "estimated_first_goal_minute": (0.10, 0.90),
    "anytime_goalscorer": (0.40, 0.60),
    "first_goalscorer": (0.40, 0.60),
}


def _pick_from_classic_snapshot(snapshot: dict[str, Any], market_id: str) -> dict[str, Any] | None:
    markets = snapshot.get("markets") or {}
    block = markets.get(market_id)
    if not isinstance(block, dict):
        return None
    final = block.get("final_selected_prediction") or block.get("tier_a_prediction") or block.get("tier_b_prediction")
    if not isinstance(final, dict):
        return None
    return final


def _pick_from_egie_snapshot(snapshot: dict[str, Any], market_id: str) -> dict[str, Any] | None:
    mapping = {
        "first_goal_team": "first_goal_team",
        "first_goal_time_range": "first_goal_time_range",
        "estimated_first_goal_minute": "estimated_first_goal_minute",
        "anytime_goalscorer": "anytime_goalscorer_candidates",
        "first_goalscorer": "first_goalscorer_candidates",
    }
    key = mapping.get(market_id)
    if not key:
        return None
    val = snapshot.get(key)
    if val is None:
        return None
    if isinstance(val, list) and val:
        return {"prediction": val[0], "confidence": snapshot.get("confidence")}
    return {"prediction": str(val), "confidence": snapshot.get("confidence")}


def _normalize_selection(sel: Any) -> str | None:
    if sel is None:
        return None
    if isinstance(sel, dict):
        return str(sel.get("prediction") or sel.get("pick") or sel.get("selection") or "")
    s = str(sel).strip()
    return s or None


def _selections_agree(a: str | None, b: str | None) -> str:
    if not a or not b:
        return "partial"
    al, bl = a.lower().strip(), b.lower().strip()
    if al == bl:
        return "agree"
    if al in bl or bl in al:
        return "partial"
    return "disagree"


def fuse_market(
    market_id: str,
    *,
    classic: dict[str, Any],
    egie: dict[str, Any],
    odds: dict[str, Any],
    features: dict[str, Any],
) -> UnifiedMarketPick:
    label = MARKET_LABELS.get(market_id, market_id.replace("_", " ").title())
    classic_snap = classic.get("market_snapshot") or {}
    egie_snap = egie.get("snapshot") or {}

    c_pick = _pick_from_classic_snapshot(classic_snap, market_id)
    e_pick = _pick_from_egie_snapshot(egie_snap, market_id)

    c_sel = _normalize_selection(c_pick.get("prediction") if c_pick else None)
    e_sel = _normalize_selection(e_pick.get("prediction") if e_pick else None)

    w_classic, w_egie = _FUSION_WEIGHTS.get(market_id, (0.6, 0.4))
    agreement = _selections_agree(c_sel, e_sel) if c_sel and e_sel else ("agree" if (c_sel or e_sel) else "partial")

    if w_egie >= 0.5 and e_sel:
        selection = e_sel
        base_conf = (e_pick or {}).get("confidence") or (c_pick or {}).get("confidence")
        source = "egie" if agreement != "disagree" else "hybrid"
    elif c_sel:
        selection = c_sel
        base_conf = (c_pick or {}).get("confidence")
        source = "classic"
    elif e_sel:
        selection = e_sel
        base_conf = (e_pick or {}).get("confidence")
        source = "egie"
    else:
        return UnifiedMarketPick(
            market_id=market_id,
            market_label=label,
            selection=None,
            status="unavailable",
            reason="no_specialist_pick",
            engine_agreement=agreement,
        )

    odds_agree = None
    if market_id == "1x2" and odds.get("status") == "ok" and selection:
        fav = odds.get("implied_favorite")
        sel_l = selection.lower()
        if fav and ("home" in sel_l or "away" in sel_l or "draw" in sel_l):
            odds_agree = fav in sel_l or (fav == "draw" and "draw" in sel_l)

    conf = compute_unified_confidence(
        base_confidence=base_conf,
        data_quality=features.get("data_quality_score"),
        engine_agreement=agreement,
        odds_agreement=odds_agree,
    )
    tier = confidence_to_tier(conf)
    explanation = build_confidence_explanation({
        "engine_agreement": agreement,
        "data_quality": features.get("data_quality_score"),
        "odds_agreement": odds_agree,
    })

    contributions = {
        "classic": c_sel,
        "egie": e_sel,
        "weights": {"classic": w_classic, "egie": w_egie},
        "odds_favorite": odds.get("implied_favorite"),
    }

    return UnifiedMarketPick(
        market_id=market_id,
        market_label=label,
        selection=selection,
        probability=(c_pick or {}).get("probability") or (e_pick or {}).get("probability"),
        confidence=conf,
        tier=tier,
        risk_level=risk_from_tier(tier, disagreement=agreement == "disagree"),
        value_signal=None,
        odds_movement=odds.get("odds_movement"),
        source_engine=source,
        engine_agreement=agreement,
        explanation=explanation,
        component_contributions=contributions,
        status="available",
    )


def select_best_tip(markets: dict[str, UnifiedMarketPick]) -> UnifiedMarketPick | None:
    ranked = [
        m for m in markets.values()
        if m.selection and m.status == "available" and m.tier in ("A", "B")
    ]
    if not ranked:
        ranked = [m for m in markets.values() if m.selection and m.status == "available"]
    if not ranked:
        return None
    ranked.sort(key=lambda m: (m.tier or "D", -(m.confidence or 0)))
    return ranked[0]


def build_combo_candidates(markets: dict[str, UnifiedMarketPick]) -> dict[str, list[dict[str, Any]]]:
    legs = [
        {
            "market_id": m.market_id,
            "market_label": m.market_label,
            "selection": m.selection,
            "confidence": m.confidence,
            "tier": m.tier,
        }
        for m in markets.values()
        if m.selection and m.tier in ("A", "B") and m.status == "available"
    ]
    legs.sort(key=lambda x: -(x.get("confidence") or 0))
    safe = [l for l in legs if l.get("tier") == "A"][:3]
    balanced = legs[:4]
    high_risk = [l for l in legs if l.get("tier") in ("B", "C")][:5]
    return {"safe": safe, "balanced": balanced, "high_risk": high_risk}
