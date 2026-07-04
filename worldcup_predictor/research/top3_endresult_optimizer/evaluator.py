"""Evaluate Top3 portfolio strategies — 90-minute results only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top3_endresult_optimizer.features import (
    is_btts,
    is_clean_sheet,
    total_goals,
    winner_side,
)


def actual_rank_in_ecse(actual: str | None, top10_lines: list[str]) -> int | None:
    if not actual:
        return None
    if actual not in top10_lines:
        return None
    return top10_lines.index(actual) + 1


def rank_bucket(rank: int | None) -> str:
    if rank is None:
        return "miss"
    if rank <= 5:
        return f"rank_{rank}"
    return "miss"


def top3_hit(actual: str | None, candidates: list[str]) -> bool:
    return bool(actual and actual in candidates[:3])


def closest_goal_error(actual: str | None, candidates: list[str]) -> float | None:
    if not actual or not candidates:
        return None
    try:
        ah, aa = map(int, actual.split("-"))
        best = min(abs((ah + aa) - (total_goals(c) or 0)) for c in candidates)
        return float(best)
    except ValueError:
        return None


def portfolio_consistency(candidates: list[str], wde: dict[str, Any]) -> dict[str, Any]:
    pick = wde.get("pick_1x2")
    btts = str(wde.get("pick_btts") or "").lower().replace("btts_", "")
    ou = str(wde.get("pick_ou25") or "").lower()

    def winner_ok(ln: str) -> bool:
        if not pick:
            return True
        side = winner_side(ln)
        return side == pick or (pick != "draw" and side == "draw")

    winner_hits = sum(1 for c in candidates if winner_ok(c))
    btts_hits = 0
    if btts == "yes":
        btts_hits = sum(1 for c in candidates if is_btts(c))
    elif btts == "no":
        btts_hits = sum(1 for c in candidates if is_clean_sheet(c))

    ou_hits = 0
    if "over" in ou:
        ou_hits = sum(1 for c in candidates if (total_goals(c) or 0) >= 3)
    elif "under" in ou:
        ou_hits = sum(1 for c in candidates if (total_goals(c) or 0) <= 2)

    return {
        "winner_direction_lines": winner_hits,
        "btts_aligned_lines": btts_hits,
        "ou_aligned_lines": ou_hits,
        "clean_sheet_lines": sum(1 for c in candidates if is_clean_sheet(c)),
        "draw_lines": sum(1 for c in candidates if winner_side(c) == "draw"),
        "high_goal_lines": sum(1 for c in candidates if (total_goals(c) or 0) >= 3),
    }


def evaluate_match_strategy(
    *,
    actual_90min: str | None,
    raw_top3: list[str],
    raw_top5: list[str],
    optimized_top3: list[str],
    top10_lines: list[str],
    wde: dict[str, Any],
    ended_aet: bool = False,
    ended_pen: bool = False,
) -> dict[str, Any]:
    rank = actual_rank_in_ecse(actual_90min, top10_lines)
    raw_hit = top3_hit(actual_90min, raw_top3)
    opt_hit = top3_hit(actual_90min, optimized_top3)
    in_top5_not_top3 = bool(
        actual_90min and actual_90min in raw_top5 and actual_90min not in raw_top3
    )

    return {
        "evaluated": actual_90min is not None,
        "actual_90min": actual_90min,
        "ended_in_extra_time": ended_aet,
        "ended_on_penalties": ended_pen,
        "actual_ecse_rank": rank,
        "actual_rank_bucket": rank_bucket(rank),
        "raw_top3_hit": raw_hit,
        "optimized_top3_hit": opt_hit,
        "raw_top5_hit": bool(actual_90min and actual_90min in raw_top5),
        "in_top5_outside_top3": in_top5_not_top3,
        "gained_vs_raw": opt_hit and not raw_hit,
        "lost_vs_raw": raw_hit and not opt_hit,
        "closest_goal_error": closest_goal_error(actual_90min, optimized_top3),
        "consistency": portfolio_consistency(optimized_top3, wde),
    }


def aggregate_strategy_metrics(rows: list[dict[str, Any]], segment: str = "all") -> dict[str, Any]:
    ev = [r for r in rows if r.get("evaluated")]
    n = len(ev)
    if not n:
        return {"segment": segment, "count": 0}

    hits = sum(1 for r in ev if r.get("optimized_top3_hit"))
    raw_hits = sum(1 for r in ev if r.get("raw_top3_hit"))
    gained = sum(1 for r in ev if r.get("gained_vs_raw"))
    lost = sum(1 for r in ev if r.get("lost_vs_raw"))

    rank_dist: dict[str, int] = {f"rank_{i}": 0 for i in range(1, 6)}
    rank_dist["miss"] = 0
    for r in ev:
        b = r.get("actual_rank_bucket") or "miss"
        rank_dist[b] = rank_dist.get(b, 0) + 1

    goal_err = [r["closest_goal_error"] for r in ev if r.get("closest_goal_error") is not None]
    cs_rate = sum(r.get("consistency", {}).get("clean_sheet_lines", 0) for r in ev) / (3 * n)

    return {
        "segment": segment,
        "count": n,
        "top3_hit_count": hits,
        "top3_hit_rate_pct": round(100 * hits / n, 1),
        "raw_top3_hit_rate_pct": round(100 * raw_hits / n, 1),
        "delta_vs_raw_top3_pp": round(100 * (hits - raw_hits) / n, 1),
        "gained_hits_vs_raw": gained,
        "lost_hits_vs_raw": lost,
        "in_top5_outside_top3_count": sum(1 for r in ev if r.get("in_top5_outside_top3")),
        "avg_closest_goal_error": round(sum(goal_err) / len(goal_err), 2) if goal_err else None,
        "avg_clean_sheet_lines_per_match": round(cs_rate * 3, 2),
        "rank_distribution": rank_dist,
        "aet_pen_count": sum(1 for r in ev if r.get("ended_in_extra_time") or r.get("ended_on_penalties")),
    }


def required_hits_for_rate(n: int, rate_pct: float) -> int:
    import math

    return math.ceil(n * rate_pct / 100.0)


def reality_check_89pct(n: int, achieved_hits: int) -> dict[str, Any]:
    required = required_hits_for_rate(n, 89.0)
    rate = round(100 * achieved_hits / n, 1) if n else 0.0
    return {
        "sample_size": n,
        "target_rate_pct": 89.0,
        "required_hits_for_89pct": required,
        "achieved_hits": achieved_hits,
        "achieved_rate_pct": rate,
        "meets_89pct": achieved_hits >= required if n else False,
        "gap_to_89pct_hits": max(0, required - achieved_hits),
        "confidence_warning": "Small sample — rates are unstable below 30–50 finished matches.",
    }
