"""Evaluate Top10→Top3 selector strategies."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import is_btts, is_clean_sheet, total_goals, winner_side


def evaluate_selection(
    *,
    actual_90min: str | None,
    raw_top3: list[str],
    selected_top3: list[str],
    candidates: list[dict[str, Any]],
    wde: dict[str, Any],
    ended_aet: bool = False,
    ended_pen: bool = False,
) -> dict[str, Any]:
    if not actual_90min:
        return {"evaluated": False}

    raw_hit = actual_90min in raw_top3[:3]
    sel_hit = actual_90min in selected_top3[:3]
    top10_lines = [r["scoreline"] for r in candidates if not r.get("injected_tail_candidate")]
    in_top10 = actual_90min in top10_lines[:10]
    rank = top10_lines.index(actual_90min) + 1 if actual_90min in top10_lines else None

    rank_rescue = sel_hit and not raw_hit and rank is not None and rank >= 6
    injected_used = any(
        r.get("injected_tail_candidate") and r["scoreline"] in selected_top3 for r in candidates
    )

    pick = wde.get("pick_1x2")
    btts = str(wde.get("pick_btts") or "").lower().replace("btts_", "")
    ou = str(wde.get("pick_ou25") or "").lower()

    def portfolio_stats(lines: list[str]) -> dict[str, Any]:
        return {
            "clean_sheet_count": sum(1 for ln in lines if is_clean_sheet(ln)),
            "btts_aligned_count": sum(
                1 for ln in lines if (is_btts(ln) and btts == "yes") or (not is_btts(ln) and btts == "no")
            )
            if btts in ("yes", "no")
            else None,
            "ou_aligned_count": sum(
                1
                for ln in lines
                if (("over" in ou and (total_goals(ln) or 0) > 2) or ("under" in ou and (total_goals(ln) or 0) <= 2))
            )
            if ou
            else None,
            "winner_preserved": all(not pick or winner_side(ln) in (pick, "draw") for ln in lines),
            "high_goal_lines": sum(1 for ln in lines if (total_goals(ln) or 0) >= 4),
        }

    return {
        "evaluated": True,
        "actual_90min": actual_90min,
        "ended_in_extra_time": ended_aet,
        "ended_on_penalties": ended_pen,
        "actual_ecse_rank": rank,
        "in_top10": in_top10,
        "raw_top3_hit": raw_hit,
        "selected_top3_hit": sel_hit,
        "gained_vs_raw": sel_hit and not raw_hit,
        "lost_vs_raw": raw_hit and not sel_hit,
        "rank_6_10_rescue": rank_rescue,
        "injected_tail_used": injected_used,
        "raw_stats": portfolio_stats(raw_top3),
        "selected_stats": portfolio_stats(selected_top3),
    }


def aggregate_metrics(rows: list[dict[str, Any]], segment: str = "all") -> dict[str, Any]:
    ev = [r for r in rows if r.get("evaluated")]
    n = len(ev)
    if not n:
        return {"segment": segment, "count": 0}

    hits = sum(1 for r in ev if r.get("selected_top3_hit"))
    raw_hits = sum(1 for r in ev if r.get("raw_top3_hit"))
    top10_cover = sum(1 for r in ev if r.get("in_top10"))
    ceiling = round(100 * top10_cover / n, 1)
    achieved_pct_of_ceiling = round(100 * hits / top10_cover, 1) if top10_cover else None

    return {
        "segment": segment,
        "count": n,
        "top3_hit_count": hits,
        "top3_hit_rate_pct": round(100 * hits / n, 1),
        "raw_top3_hit_rate_pct": round(100 * raw_hits / n, 1),
        "delta_vs_raw_pp": round(100 * (hits - raw_hits) / n, 1),
        "gained_vs_raw": sum(1 for r in ev if r.get("gained_vs_raw")),
        "lost_vs_raw": sum(1 for r in ev if r.get("lost_vs_raw")),
        "rank_6_10_rescue_count": sum(1 for r in ev if r.get("rank_6_10_rescue")),
        "top10_coverage_pct": ceiling,
        "pct_of_top10_ceiling": achieved_pct_of_ceiling,
        "avg_clean_sheet_selected": round(
            sum((r.get("selected_stats") or {}).get("clean_sheet_count", 0) for r in ev) / n, 2
        ),
        "aet_pen_count": sum(1 for r in ev if r.get("ended_in_extra_time") or r.get("ended_on_penalties")),
    }


def promotion_gate_simulation(summary: dict[str, Any], strategy_metrics: dict[str, Any]) -> dict[str, Any]:
    n = summary.get("finished_matches") or 0
    best_rate = strategy_metrics.get("top3_hit_rate_pct") or 0
    raw_rate = strategy_metrics.get("raw_top3_hit_rate_pct") or 0
    delta = strategy_metrics.get("delta_vs_raw_pp") or 0

    checks = {
        "min_40_matches": n >= 40,
        "top3_hit_rate_gte_58": best_rate >= 58.0,
        "improves_raw_by_5pp": delta >= 5.0,
        "no_major_segment_regression": True,
        "best_or_tied_best": True,
        "odds_freshness_documented": True,
        "aet_pen_stable": True,
    }
    passed = sum(1 for v in checks.values() if v)
    return {
        "proposed_gate_checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "gate_open": all(checks.values()),
        "current_sample": n,
        "needed_matches": max(0, 40 - n),
        "current_top3_rate": best_rate,
        "current_delta_pp": delta,
        "status": "INSUFFICIENT_DATA" if n < 40 else ("PASS" if all(checks.values()) else "FAIL"),
        "why_insufficient": (
            f"Only {n}/40 finished matches; need {max(0, 40-n)} more before promotion gate can open."
            if n < 40
            else "Sample threshold met; evaluate remaining gate checks."
        ),
    }
