"""Diagnose Top5 misses and root-cause categories."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top10_coverage.features import actual_outcome


def _wde_correct(wde: dict[str, Any], outcome: dict[str, Any]) -> dict[str, bool | None]:
    pick = wde.get("pick_1x2")
    btts = str(wde.get("pick_btts") or "").lower().replace("btts_", "")
    ou = str(wde.get("pick_ou25") or "").lower()
    return {
        "wde_1x2_correct": pick == outcome.get("winner") if pick and outcome.get("winner") else None,
        "wde_btts_correct": btts == outcome.get("btts") if btts in ("yes", "no") else None,
        "wde_ou_correct": (
            ("over" in ou and outcome.get("over_25") == "over_2_5")
            or ("under" in ou and outcome.get("over_25") == "under_2_5")
        )
        if ou
        else None,
    }


def classify_root_cause(match: dict[str, Any]) -> str:
    cov = match.get("coverage") or {}
    outcome = match.get("outcome") or {}
    freshness = match.get("odds_freshness") or {}
    res = match.get("result_context") or {}

    if not match.get("actual_90min"):
        return "DATA_MISSING"

    rank = cov.get("rank_effective")
    in_top5 = cov.get("in_top5_snapshot")
    in_top10 = cov.get("in_top10_snapshot")
    in_top20 = cov.get("in_top20_distribution")
    in_full = cov.get("in_full_distribution")

    if not in_full and not in_top10:
        tg = outcome.get("total_goals") or 0
        if tg >= 5:
            return "HIGH_GOAL_TAIL_MISSING"
        if tg >= 4:
            return "HIGH_GOAL_TAIL_MISSING"
        if outcome.get("winner") == "draw":
            return "DRAW_RISK_MISSING"
        if outcome.get("btts") == "yes":
            return "BTTS_SCORE_MISSING"
        return "ACTUAL_OUTSIDE_TOP10_CANDIDATE_PROBLEM"

    if res.get("ended_in_extra_time") or res.get("ended_on_penalties"):
        if not in_top5 and in_top10:
            pass  # ranking at 90' — not an eval-split issue
        elif not in_top10 and not in_full:
            return "ACTUAL_OUTSIDE_TOP10_CANDIDATE_PROBLEM"

    if in_top10 and not in_top5:
        return "ACTUAL_IN_TOP10_RANKING_PROBLEM"

    if in_top20 and not in_top10:
        return "ACTUAL_IN_TOP10_RANKING_PROBLEM"  # rank 11-20 band when distribution linked

    if rank is None and not in_full:
        return "ACTUAL_OUTSIDE_TOP10_CANDIDATE_PROBLEM"

    if freshness.get("stale_odds") or freshness.get("freshness_flag") == "STALE_ODDS":
        if not in_top5:
            return "STALE_ODDS_LAMBDA"

    if not in_top5:
        tg = outcome.get("total_goals") or 0
        if tg >= 4:
            return "HIGH_GOAL_TAIL_MISSING"
        if outcome.get("btts") == "yes":
            return "BTTS_SCORE_MISSING"
        if outcome.get("winner") == "draw":
            return "DRAW_RISK_MISSING"
        return "ACTUAL_OUTSIDE_TOP10_CANDIDATE_PROBLEM"

    return "ACTUAL_IN_TOP10_RANKING_PROBLEM"


def miss_due_to_ranking_or_absence(match: dict[str, Any], *, topn: int) -> str:
    cov = match.get("coverage") or {}
    actual = match.get("actual_90min")
    if not actual:
        return "unavailable"
    lines = cov.get("snapshot_top10") or []
    if actual in lines[:topn]:
        return "hit"
    if actual in lines[:10]:
        return "ranking"
    if cov.get("in_top20_distribution"):
        return "ranking_beyond_top10"
    if cov.get("in_full_distribution"):
        return "ranking_beyond_top20"
    return "candidate_absence"


def diagnose_top5_miss(match: dict[str, Any]) -> dict[str, Any] | None:
    cov = match.get("coverage") or {}
    if cov.get("in_top5_snapshot"):
        return None
    outcome = actual_outcome(match.get("actual_90min"))
    wde = match.get("wde") or {}
    root = classify_root_cause(match)
    return {
        "match": match.get("match"),
        "fixture_id": match.get("fixture_id"),
        "actual_90min": match.get("actual_90min"),
        "aet_pen": bool(
            (match.get("result_context") or {}).get("ended_in_extra_time")
            or (match.get("result_context") or {}).get("ended_on_penalties")
        ),
        "ecse_top5": cov.get("snapshot_top5"),
        "ecse_top10": cov.get("snapshot_top10"),
        "distribution_top20": cov.get("distribution_top20"),
        "actual_rank_snapshot": cov.get("rank_in_snapshot"),
        "actual_rank_distribution": cov.get("rank_in_distribution"),
        "actual_total_goals": outcome.get("total_goals"),
        "actual_btts": outcome.get("btts"),
        "actual_winner": outcome.get("winner"),
        **_wde_correct(wde, outcome),
        "odds_freshness_flag": (match.get("odds_freshness") or {}).get("freshness_flag"),
        "root_cause_category": root,
        "miss_type": miss_due_to_ranking_or_absence(match, topn=5),
    }
