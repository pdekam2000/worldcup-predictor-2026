"""Bookmaker / market completeness metrics for Correct Score."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.correct_score_odds.store import best_odds_map, single_bookmaker_maps
from worldcup_predictor.research.correct_score_odds.statuses import (
    ANY_OTHER_AWAY,
    ANY_OTHER_DRAW,
    ANY_OTHER_HOME,
)


def overround_proxy(odds_by_sel: dict[str, float]) -> float | None:
    if not odds_by_sel:
        return None
    inv = sum(1.0 / o for o in odds_by_sel.values() if o and o > 1)
    return inv


def fixture_completeness(
    conn,
    fixture_id: int,
    *,
    top5: list[str] | None = None,
    top10: list[str] | None = None,
    shifted: list[str] | None = None,
) -> dict[str, Any]:
    best = best_odds_map(conn, fixture_id)
    exact = {k: v for k, v in best.items() if "-" in k and k[0].isdigit()}
    scores = list(exact.keys())
    goals = []
    for s in scores:
        try:
            h, a = s.split("-")
            goals.append((int(h), int(a)))
        except Exception:
            pass
    bm_maps = single_bookmaker_maps(conn, fixture_id)
    # any-other from lines
    any_other = set()
    for r in conn.execute(
        """
        SELECT DISTINCT selection FROM correct_score_odds_lines
        WHERE fixture_id = ? AND selection LIKE 'ANY_OTHER%'
        """,
        (fixture_id,),
    ):
        any_other.add(str(r["selection"]))

    top5 = top5 or []
    top10 = top10 or []
    shifted = shifted or []
    missing_top5 = [s for s in top5 if s not in exact]
    missing_top10 = [s for s in top10 if s not in exact]
    missing_shifted = [s for s in shifted if s not in exact]

    # best single-bookmaker coverage of top5
    best_single = None
    best_single_n = -1
    for bm, m in bm_maps.items():
        n = sum(1 for s in top5 if s in m)
        if n > best_single_n:
            best_single_n = n
            best_single = bm

    return {
        "fixture_id": fixture_id,
        "n_bookmakers": len(bm_maps),
        "n_exact_scores_quoted_best": len(exact),
        "lowest_score_quoted": min(scores, key=lambda s: (int(s.split("-")[0]) + int(s.split("-")[1]), s)) if scores else None,
        "highest_score_quoted": max(scores, key=lambda s: (int(s.split("-")[0]) + int(s.split("-")[1]), s)) if scores else None,
        "missing_top5": "|".join(missing_top5),
        "missing_top5_n": len(missing_top5),
        "missing_top10": "|".join(missing_top10),
        "missing_top10_n": len(missing_top10),
        "missing_shifted": "|".join(missing_shifted),
        "any_other_home": int(ANY_OTHER_HOME in any_other),
        "any_other_draw": int(ANY_OTHER_DRAW in any_other),
        "any_other_away": int(ANY_OTHER_AWAY in any_other),
        "market_overround_proxy": overround_proxy({k: float(v["decimal_odds"]) for k, v in exact.items()}),
        "best_single_bookmaker_for_top5": best_single,
        "best_single_bookmaker_top5_n": best_single_n,
        "cross_bookmaker_top5_n": len(top5) - len(missing_top5),
        "portfolio_mode_if_top5_complete_single": (
            "SINGLE_BOOKMAKER_PORTFOLIO" if best_single_n == len(top5) and top5 else "BEST_ODDS_CROSS_BOOKMAKER_PORTFOLIO"
        ),
        "outcome_space_complete": False,
        "note": "Top5/Top10 CS subsets are never a complete exact-score outcome space",
    }
