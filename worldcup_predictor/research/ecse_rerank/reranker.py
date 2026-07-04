"""Shadow ECSE Top-10 re-ranker — does not mutate production rows."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import PHASE, parse_top10
from worldcup_predictor.research.ecse_rerank.scorer import apply_stale_confidence, compute_shadow_boosts

SHADOW_LABEL = "SHADOW_ONLY"
PUBLIC_PUBLISH = False


def rerank_ecse_top10_shadow(
    *,
    top_10: list[dict[str, Any]] | Any,
    wde_1x2: str | None = None,
    wde_btts: str | None = None,
    wde_ou25: str | None = None,
    ecse_top1: str | None = None,
    odds_freshness: dict[str, Any] | None = None,
    fixture_id: int | None = None,
) -> dict[str, Any]:
    """
    Re-rank ECSE candidates using WDE market consistency boosts.
    Preserves all Top-10 scorelines; only shadow rank/order changes.
    """
    candidates = parse_top10(top_10)
    if not candidates:
        return {
            "phase": PHASE,
            "fixture_id": fixture_id,
            "shadow_only": True,
            "PUBLIC_PUBLISH": PUBLIC_PUBLISH,
            "error": "NO_CANDIDATES",
        }

    freshness = odds_freshness or {}
    stale = bool(freshness.get("stale_odds"))
    freshness_flag = freshness.get("freshness_flag") or "ODDS_FRESHNESS_UNKNOWN"
    requires_fresh = stale or freshness_flag == "ODDS_FRESHNESS_UNKNOWN"

    baseline_top1 = candidates[0]["scoreline"]
    ecse_top1_line = ecse_top1 or baseline_top1

    reranked: list[dict[str, Any]] = []
    for c in candidates:
        line = c["scoreline"]
        base_p = float(c.get("probability") or 0.0)
        boost = compute_shadow_boosts(
            scoreline=line,
            wde_1x2=wde_1x2,
            wde_btts=wde_btts,
            wde_ou=wde_ou25,
            ecse_top1=ecse_top1_line,
            stale_odds=stale,
        )
        shadow_p = base_p * boost["boost_factor"]
        reranked.append(
            {
                **c,
                "baseline_probability": round(base_p, 6),
                "shadow_probability": round(shadow_p, 6),
                "boost_factor": boost["boost_factor"],
                "boost_reasons": boost["reasons"],
                "baseline_rank": c.get("rank"),
            }
        )

    reranked.sort(key=lambda x: (-x["shadow_probability"], x["baseline_rank"] or 99))
    for i, row in enumerate(reranked, 1):
        row["shadow_rank"] = i

    shadow_top1 = reranked[0]["scoreline"]
    shadow_top3 = [r["scoreline"] for r in reranked[:3]]
    shadow_top5 = [r["scoreline"] for r in reranked[:5]]

    consistency_notes: list[str] = []
    if wde_btts == "yes" and is_clean_sheet(ecse_top1_line):
        consistency_notes.append("BTTS_YES_VS_CLEAN_SHEET_TOP1")
    if wde_ou25 == "over_2_5" and (total_goals_safe(ecse_top1_line) or 0) <= 2:
        consistency_notes.append("OVER25_VS_LOW_SCORE_TOP1")
    if requires_fresh:
        consistency_notes.append("REQUIRES_FRESH_ODDS")

    base_conf = reranked[0]["baseline_probability"]
    shadow_conf = reranked[0]["shadow_probability"]
    adj_conf = apply_stale_confidence(shadow_conf, stale)

    return {
        "phase": PHASE,
        "fixture_id": fixture_id,
        "shadow_only": True,
        "PUBLIC_PUBLISH": PUBLIC_PUBLISH,
        "baseline": {
            "top_1": baseline_top1,
            "top_3": [c["scoreline"] for c in sorted(candidates, key=lambda x: x.get("rank", 99))[:3]],
            "top_5": [c["scoreline"] for c in sorted(candidates, key=lambda x: x.get("rank", 99))[:5]],
        },
        "shadow": {
            "top_1": shadow_top1,
            "top_3": shadow_top3,
            "top_5": shadow_top5,
            "top_10": reranked,
            "confidence_score": adj_conf,
            "recommendation_flag": "REQUIRES_FRESH_ODDS" if requires_fresh else "SHADOW_RERANK_OK",
        },
        "rank_changed": shadow_top1 != baseline_top1,
        "odds_freshness": freshness,
        "wde_inputs": {"pick_1x2": wde_1x2, "pick_btts": wde_btts, "pick_ou25": wde_ou25},
        "consistency_notes": consistency_notes,
        "confidence_delta": round((adj_conf or 0) - (base_conf or 0), 6),
    }


def is_clean_sheet(line: str) -> bool:
    from worldcup_predictor.research.ecse_rerank.features import is_clean_sheet as _ics

    return _ics(line)


def total_goals_safe(line: str | None) -> int | None:
    from worldcup_predictor.research.ecse_rerank.features import total_goals

    return total_goals(line) if line else None
