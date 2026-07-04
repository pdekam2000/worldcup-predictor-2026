"""Match features for Top3 End Result optimizer — read-only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import (
    extract_wde_markets,
    is_btts,
    is_clean_sheet,
    is_knockout_fixture,
    odds_freshness_meta,
    parse_scoreline,
    parse_top10,
    result_context,
    total_goals,
    winner_side,
)

PHASE = "TOP3-ENDRESULT-OPTIMIZER-1"

__all__ = [
    "PHASE",
    "extract_wde_markets",
    "is_btts",
    "is_clean_sheet",
    "is_knockout_fixture",
    "odds_freshness_meta",
    "parse_scoreline",
    "parse_top10",
    "result_context",
    "total_goals",
    "winner_side",
    "match_archetype",
    "draw_risk_score",
]


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


def draw_risk_score(wde: dict[str, Any]) -> float:
    """Higher = more draw-risk from WDE signals."""
    score = 0.0
    if wde.get("pick_1x2") == "draw":
        score += 0.6
    prob_draw = wde.get("prob_draw")
    if prob_draw is not None:
        try:
            p = float(prob_draw)
            if p <= 1:
                p *= 100
            score += min(0.4, p / 100.0)
        except (TypeError, ValueError):
            pass
    return min(1.0, score)


def match_archetype(wde: dict[str, Any]) -> str:
    """Classify match for Strategy 3 archetype selection."""
    pick = wde.get("pick_1x2")
    btts = _norm_btts(wde.get("pick_btts"))
    ou = _norm_ou(wde.get("pick_ou25"))
    draw_risk = draw_risk_score(wde)

    if pick == "away_win":
        return "underdog_away"
    if draw_risk >= 0.45:
        return "draw_risk"
    if pick == "home_win":
        if ou == "under_2_5" and btts == "no":
            return "favorite_under_btts_no"
        if ou == "over_2_5" and btts == "yes":
            return "favorite_over_btts_yes"
        if ou == "over_2_5" and btts == "no":
            return "favorite_over_btts_no"
        if btts == "yes":
            return "favorite_btts_yes"
    if pick == "draw":
        return "draw_risk"
    return "balanced"
