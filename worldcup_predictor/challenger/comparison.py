"""Canonical vs Challenger comparison helpers (non-authoritative)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.challenger.constants import CONFLICT_CLASSES


def _argmax_1x2(probs: dict[str, Any] | None) -> str | None:
    if not probs:
        return None
    mapping = {
        "home": probs.get("home") or probs.get("home_win") or probs.get("home_probability"),
        "draw": probs.get("draw") or probs.get("draw_probability"),
        "away": probs.get("away") or probs.get("away_win") or probs.get("away_probability"),
    }
    vals = {k: float(v) for k, v in mapping.items() if v is not None}
    if not vals:
        return None
    return max(vals, key=vals.get)


def classify_conflict(canonical: dict[str, Any], challenger: dict[str, Any]) -> str:
    c_1x2 = canonical.get("wde_decision") or _argmax_1x2(canonical.get("hda"))
    g_1x2 = challenger.get("decision_1x2") or _argmax_1x2((challenger.get("output_probabilities") or {}).get("hda"))
    if not c_1x2 or not g_1x2:
        return "INSUFFICIENT_DATA"
    if c_1x2 != g_1x2:
        return "DIRECTION_CONFLICT"
    c_ou = str(canonical.get("ou25") or "").lower()
    g_ou = str((challenger.get("output_probabilities") or {}).get("ou25_selection") or "").lower()
    if c_ou and g_ou and (("over" in c_ou) != ("over" in g_ou)):
        return "GOAL_MARKET_CONFLICT"
    c_top1 = canonical.get("ecse_top1")
    g_top1 = (challenger.get("output_probabilities") or {}).get("top1_score")
    if c_top1 and g_top1 and str(c_top1) != str(g_top1):
        return "SCORE_DISTRIBUTION_CONFLICT"
    return "STRONG_AGREEMENT" if c_top1 == g_top1 else "MODERATE_AGREEMENT"


def build_prematch_comparison(canonical: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    conflict = classify_conflict(canonical, challenger)
    assert conflict in CONFLICT_CLASSES
    ch_out = challenger.get("output_probabilities") or {}
    return {
        "same_1x2_direction": (canonical.get("wde_decision") or "")
        == (ch_out.get("decision_1x2") or challenger.get("decision_1x2") or ""),
        "btts_agreement": canonical.get("btts") == ch_out.get("btts_selection"),
        "ou_agreement": str(canonical.get("ou25") or "").lower() in str(ch_out.get("ou25_selection") or "").lower()
        or str(canonical.get("ou25") or "") == str(ch_out.get("ou25_selection") or ""),
        "top1_agreement": str(canonical.get("ecse_top1") or "") == str(ch_out.get("top1_score") or ""),
        "conflict_class": conflict,
        "canonical_freeze_hash": canonical.get("freeze_hash"),
        "challenger_freeze_hash": challenger.get("freeze_hash") or challenger.get("prediction_content_hash"),
        "winner_before_result": None,
    }
