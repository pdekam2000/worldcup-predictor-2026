"""Forward evaluator — compare frozen challenger vs confirmed results only."""

from __future__ import annotations

from typing import Any


def evaluate_against_actual(challenger_outputs: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """actual: home_goals, away_goals, score, result_1x2, btts, over25"""
    out = challenger_outputs or {}
    score = actual.get("score")
    top5 = [t.get("score") for t in (out.get("top5") or [])]
    top10 = [t.get("score") for t in (out.get("top10") or [])]
    return {
        "hit_1x2": out.get("decision_1x2") == actual.get("result_1x2"),
        "hit_btts": out.get("btts_selection") == ("yes" if actual.get("btts") else "no"),
        "hit_ou25": ("over" in str(out.get("ou25_selection")) and actual.get("over25"))
        or ("under" in str(out.get("ou25_selection")) and not actual.get("over25")),
        "top1": bool(top5) and top5[0] == score,
        "top3": score in top5[:3],
        "top5": score in top5[:5],
        "top10": score in top10[:10],
        "actual_rank": (top10.index(score) + 1) if score in top10 else "OUTSIDE_TOP10",
    }
