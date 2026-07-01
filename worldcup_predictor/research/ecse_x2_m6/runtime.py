"""PHASE ECSE-X2-M6 — Shadow-live shortlist enhancer runtime."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_x2_m3.equation import compute_log_home_prob_phi
from worldcup_predictor.research.ecse_x2_m4.segment import (
    classify_match_state,
    is_strong_home_favorite,
    odds_snapshot_valid,
)
from worldcup_predictor.research.ecse_x2_m5.methods import apply_shortlist_enhancer
from worldcup_predictor.research.ecse_x2_m5.metrics import segment_labels
from worldcup_predictor.research.ecse_x2_m6.constants import (
    EQUATION_NAME,
    MIN_HOME_PROB_PREFERRED,
    METHOD_VERSION,
    SHORTLIST_TOP_N,
)


def _normalize_top10(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda x: int(x.get("rank", 999)))
    out = []
    for i, r in enumerate(sorted_rows, start=1):
        out.append(
            {
                "scoreline": str(r["scoreline"]),
                "probability": round(float(r["probability"]), 8),
                "rank": int(r.get("rank", i)),
                "home_goals": r.get("home_goals"),
                "away_goals": r.get("away_goals"),
            }
        )
    return out[:SHORTLIST_TOP_N]


def _membership_unchanged(baseline: list[dict[str, Any]], enhanced: list[dict[str, Any]]) -> bool:
    base_set = {str(r["scoreline"]) for r in baseline}
    enh_set = {str(r["scoreline"]) for r in enhanced}
    return base_set == enh_set


def _rank_movements(
    baseline: list[dict[str, Any]], enhanced: list[dict[str, Any]]
) -> dict[str, int]:
    b_rank = {str(r["scoreline"]): int(r["rank"]) for r in baseline}
    e_rank = {str(r["scoreline"]): int(r["rank"]) for r in enhanced}
    moves: dict[str, int] = {}
    for sl in b_rank:
        if sl in e_rank and b_rank[sl] != e_rank[sl]:
            moves[sl] = b_rank[sl] - e_rank[sl]
    return moves


def evaluate_eligibility(
    *,
    baseline_top10: list[dict[str, Any]],
    probs: dict[str, float | None],
    coverage: int,
) -> tuple[bool, str | None]:
    if not baseline_top10:
        return False, "missing_baseline_top10"
    if len(baseline_top10) < SHORTLIST_TOP_N:
        return False, "incomplete_baseline_top10"
    home = probs.get("ft_home")
    if home is None or not math.isfinite(home) or home <= 0:
        return False, "missing_ft_home"
    if not odds_snapshot_valid(probs, coverage):
        return False, "invalid_odds_snapshot"
    eq = compute_log_home_prob_phi(probs)
    if eq is None or not math.isfinite(eq):
        return False, "invalid_equation_value"
    state = classify_match_state(probs)
    if state == "balanced":
        return False, "balanced_match"
    if home < MIN_HOME_PROB_PREFERRED:
        return False, "home_prob_below_55"
    if state != "home_favorite":
        return False, "not_home_favorite"
    return True, None


def compute_shadow_live_shortlist(
    *,
    fixture_id: int,
    baseline_top10: list[dict[str, Any]],
    probs: dict[str, float | None],
    lift_model: dict[str, Any] | None,
    coverage: int = 0,
    fixture_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Safe runtime: never mutates baseline; returns shadow enhanced shortlist."""
    meta = fixture_metadata or {}
    baseline = _normalize_top10(baseline_top10)
    home = probs.get("ft_home")
    home_prob = round(float(home), 6) if home is not None and math.isfinite(home) else None
    eq_val = compute_log_home_prob_phi(probs)
    labels = segment_labels(probs, home_prob=home_prob)

    eligible, exclusion = evaluate_eligibility(
        baseline_top10=baseline, probs=probs, coverage=coverage
    )
    audit: list[str] = ["baseline_top10_loaded"]

    if not eligible or lift_model is None:
        if lift_model is None and eligible:
            exclusion = exclusion or "lift_model_unavailable"
        audit.append(f"excluded:{exclusion or 'not_eligible'}")
        return {
            "fixture_id": fixture_id,
            "method_version": METHOD_VERSION,
            "equation_name": EQUATION_NAME,
            "baseline_top10": baseline,
            "enhanced_top10": baseline,
            "applied": False,
            "exclusion_reason": exclusion or "not_eligible",
            "home_prob": home_prob,
            "equation_value": round(eq_val, 8) if eq_val is not None else None,
            "segment_labels": labels,
            "strong_segment": is_strong_home_favorite(probs),
            "rank_movements": {},
            "membership_unchanged": True,
            "public_output_changed": False,
            "audit_trace": audit,
            "kickoff_time": meta.get("kickoff_utc"),
            "league": meta.get("league") or meta.get("competition_key"),
            "tournament": meta.get("tournament") or meta.get("competition_key"),
        }

    audit.append("lift_model_ready")
    audit.append("shortlist_enhancer_apply")
    enhanced = apply_shortlist_enhancer(
        baseline, eq_val=eq_val, model=lift_model, top_n=SHORTLIST_TOP_N
    )
    membership_ok = _membership_unchanged(baseline, enhanced)
    if not membership_ok:
        audit.append("membership_guard_triggered")
        enhanced = baseline
        return {
            "fixture_id": fixture_id,
            "method_version": METHOD_VERSION,
            "equation_name": EQUATION_NAME,
            "baseline_top10": baseline,
            "enhanced_top10": baseline,
            "applied": False,
            "exclusion_reason": "membership_would_change",
            "home_prob": home_prob,
            "equation_value": round(eq_val, 8),
            "segment_labels": labels,
            "strong_segment": is_strong_home_favorite(probs),
            "rank_movements": {},
            "membership_unchanged": False,
            "public_output_changed": False,
            "audit_trace": audit,
            "kickoff_time": meta.get("kickoff_utc"),
            "league": meta.get("league") or meta.get("competition_key"),
            "tournament": meta.get("tournament") or meta.get("competition_key"),
        }

    moves = _rank_movements(baseline, enhanced)
    audit.append(f"reordered:{len(moves)}_scorelines")
    return {
        "fixture_id": fixture_id,
        "method_version": METHOD_VERSION,
        "equation_name": EQUATION_NAME,
        "baseline_top10": baseline,
        "enhanced_top10": enhanced,
        "applied": True,
        "exclusion_reason": None,
        "home_prob": home_prob,
        "equation_value": round(eq_val, 8),
        "segment_labels": labels,
        "strong_segment": is_strong_home_favorite(probs),
        "rank_movements": moves,
        "membership_unchanged": True,
        "public_output_changed": False,
        "audit_trace": audit,
        "kickoff_time": meta.get("kickoff_utc"),
        "league": meta.get("league") or meta.get("competition_key"),
        "tournament": meta.get("tournament") or meta.get("competition_key"),
    }
