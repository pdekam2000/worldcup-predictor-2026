"""PHASE ECSE-X2-M3 — Champion vs challenger shadow scorer."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x2_m3.equation import compute_log_home_prob_phi
from worldcup_predictor.research.ecse_x2_m2.reorder import apply_reorder, learn_lift_table, score_cluster


def _top_n(dist: list[dict[str, Any]], n: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "scoreline": r["scoreline"],
            "probability": round(float(r["probability"]), 8),
            "rank": int(r["rank"]),
        }
        for r in sorted(dist, key=lambda x: int(x["rank"]))[:n]
    ]


def score_fixture_shadow(
    *,
    dist_rows: list[dict[str, Any]],
    probs: dict[str, float | None],
    lift_model: dict[str, Any] | None,
    top_n: int = 10,
) -> dict[str, Any]:
    baseline = [dict(r) for r in dist_rows]
    baseline_top = _top_n(baseline, top_n)

    eq_val = compute_log_home_prob_phi(probs)
    if eq_val is None or lift_model is None:
        return {
            "eligible": False,
            "equation_value": None,
            "baseline_top": baseline_top,
            "challenger_top": baseline_top,
            "top1_disagreement": False,
            "rank_movements": {},
        }

    challenger = apply_reorder(baseline, value=eq_val, model=lift_model)
    challenger_top = _top_n(challenger, top_n)

    base_top1 = baseline_top[0]["scoreline"] if baseline_top else None
    chal_top1 = challenger_top[0]["scoreline"] if challenger_top else None

    rank_movements: dict[str, int] = {}
    base_rank = {r["scoreline"]: r["rank"] for r in baseline_top}
    chal_rank = {r["scoreline"]: r["rank"] for r in challenger_top}
    for sl in set(base_rank) | set(chal_rank):
        if sl in base_rank and sl in chal_rank:
            rank_movements[sl] = int(base_rank[sl]) - int(chal_rank[sl])

    return {
        "eligible": True,
        "equation_value": round(eq_val, 8),
        "baseline_top": baseline_top,
        "challenger_top": challenger_top,
        "top1_disagreement": base_top1 != chal_top1,
        "rank_movements": rank_movements,
    }


def build_lift_model(train_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    train_vals = []
    for row in train_rows:
        val = compute_log_home_prob_phi(row["probs"])
        if val is None:
            continue
        train_vals.append(
            {
                "value": val,
                "actual": row["actual"],
                "actual_cluster": score_cluster(row["actual"]),
            }
        )
    if len(train_vals) < 500:
        return None
    return learn_lift_table(train_vals)
