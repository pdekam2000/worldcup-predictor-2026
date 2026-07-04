"""Shadow score adjustments for ECSE re-rank — advisory only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import (
    BTTS_BOOST_LINES,
    CLEAN_SHEET_LINES,
    FAVORITE_MARGIN_BTTS,
    OVER_BOOST_LINES,
    is_btts,
    is_clean_sheet,
    total_goals,
    winner_side,
)

# Multiplicative boosts (shadow tuning — not production lambda)
BTTS_YES_BOOST = 1.35
OVER25_BOOST = 1.30
FAVORITE_MARGIN_BOOST = 1.25
UNDER_BTTS_NO_BOOST = 1.20
WINNER_CONFLICT_PENALTY = 0.55
STALE_ODDS_CONFIDENCE_FACTOR = 0.85


def _norm_btts(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).lower().replace("btts_", "")
    return v if v in ("yes", "no") else None


def _norm_ou(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).lower()
    if "over" in v:
        return "over_2_5"
    if "under" in v:
        return "under_2_5"
    return v


def compute_shadow_boosts(
    *,
    scoreline: str,
    wde_1x2: str | None,
    wde_btts: str | None,
    wde_ou: str | None,
    ecse_top1: str | None,
    stale_odds: bool,
) -> dict[str, Any]:
    """Return boost factor and reason tags for one candidate scoreline."""
    reasons: list[str] = []
    factor = 1.0

    btts = _norm_btts(wde_btts)
    ou = _norm_ou(wde_ou)
    tg = total_goals(scoreline) or 0

    # Rule 1: BTTS Yes vs clean-sheet Top1
    if btts == "yes" and ecse_top1 and is_clean_sheet(ecse_top1):
        if scoreline in BTTS_BOOST_LINES or is_btts(scoreline):
            factor *= BTTS_YES_BOOST
            reasons.append("btts_yes_boost")

    # Rule 2: Over 2.5 vs low-score Top1
    if ou == "over_2_5" and ecse_top1 and (total_goals(ecse_top1) or 0) <= 2:
        if scoreline in OVER_BOOST_LINES or tg >= 3:
            factor *= OVER25_BOOST
            reasons.append("over25_boost")

    # Rule 3: Preserve WDE winner direction
    if wde_1x2 and wde_1x2 in ("home_win", "away_win", "draw"):
        side = winner_side(scoreline)
        if side and side != wde_1x2:
            # Only penalize if WDE winner is clear (not draw pick on non-draw line)
            if wde_1x2 != "draw" or side != "draw":
                factor *= WINNER_CONFLICT_PENALTY
                reasons.append("winner_direction_penalty")

    # Rule 4: Favorite win + BTTS Yes → one-goal-margin wins
    if btts == "yes" and wde_1x2 in ("home_win", "away_win"):
        if scoreline in FAVORITE_MARGIN_BTTS and winner_side(scoreline) == wde_1x2:
            factor *= FAVORITE_MARGIN_BOOST
            reasons.append("favorite_margin_btts_boost")

    # Rule 5: Under + BTTS No → clean sheets
    if ou == "under_2_5" and btts == "no":
        if scoreline in CLEAN_SHEET_LINES or is_clean_sheet(scoreline):
            factor *= UNDER_BTTS_NO_BOOST
            reasons.append("under_btts_no_boost")

    if stale_odds:
        reasons.append("stale_odds_discount")

    return {"boost_factor": round(factor, 4), "reasons": reasons}


def apply_stale_confidence(confidence: float | None, stale: bool) -> float | None:
    if confidence is None:
        return None
    if stale:
        return round(confidence * STALE_ODDS_CONFIDENCE_FACTOR, 4)
    return confidence
