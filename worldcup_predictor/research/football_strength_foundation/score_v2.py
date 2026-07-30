"""Score distribution V2 helpers and simple rank calibration (shadow)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import (
    generate_score_distribution,
    poisson_pmf,
)


def dist_poisson(lh: float, la: float, max_goals: int = 7) -> list[dict[str, Any]]:
    return generate_score_distribution(lh, la, max_goals=max_goals, use_dixon_coles=False)


def dist_dc(lh: float, la: float, max_goals: int = 7) -> list[dict[str, Any]]:
    return generate_score_distribution(lh, la, max_goals=max_goals, use_dixon_coles=True)


def dist_overdispersed(lh: float, la: float, *, alpha: float = 0.15, max_goals: int = 7) -> list[dict[str, Any]]:
    """NB-like mixture: average Poisson at (1±alpha) scales (conditional overdispersion)."""
    scales = (1.0 - alpha, 1.0, 1.0 + alpha)
    acc: dict[tuple[int, int], float] = defaultdict(float)
    other = 0.0
    for s in scales:
        d = generate_score_distribution(lh * s, la * s, max_goals=max_goals)
        for e in d:
            if e["scoreline"] == "OTHER":
                other += float(e["probability"]) / len(scales)
            else:
                acc[(int(e["home_goals"]), int(e["away_goals"]))] += float(e["probability"]) / len(scales)
    rows = [
        {
            "scoreline": f"{h}-{a}",
            "home_goals": h,
            "away_goals": a,
            "probability": p,
        }
        for (h, a), p in acc.items()
    ]
    rows.append({"scoreline": "OTHER", "home_goals": -1, "away_goals": -1, "probability": other})
    rows.sort(key=lambda x: -x["probability"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def exact_metrics(dist: list[dict[str, Any]], ah: int, aa: int) -> dict[str, Any]:
    label = f"{ah}-{aa}"
    tops = [e["scoreline"] for e in dist if e.get("scoreline") != "OTHER"]
    rank = None
    p_act = None
    for e in dist:
        if e.get("scoreline") == label:
            rank = int(e["rank"])
            p_act = float(e["probability"])
            break
    ll = -math.log(max(p_act or 1e-12, 1e-12))
    return {
        "top1": bool(tops and tops[0] == label),
        "top3": label in tops[:3],
        "top5": label in tops[:5],
        "top10": label in tops[:10],
        "rank": rank,
        "p_actual": p_act,
        "log_loss": ll,
        "tops": tops[:10],
    }


def rank_bias_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """rows need predicted_rank and actual scoreline label."""
    targets = [
        "0-0",
        "1-0",
        "0-1",
        "1-1",
        "2-0",
        "0-2",
        "2-1",
        "1-2",
        "2-2",
        "3-0",
        "0-3",
        "3-1",
        "1-3",
        "3-2",
        "2-3",
        "4-0",
        "0-4",
    ]
    out = []
    for lab in targets:
        sub = [r for r in rows if r.get("actual_score") == lab]
        if not sub:
            out.append({"scoreline": lab, "n": 0})
            continue
        ranks = [r["predicted_rank"] for r in sub if r.get("predicted_rank") is not None]
        out.append(
            {
                "scoreline": lab,
                "n": len(sub),
                "mean_predicted_rank": sum(ranks) / len(ranks) if ranks else None,
                "median_predicted_rank": sorted(ranks)[len(ranks) // 2] if ranks else None,
                "top5_rate": sum(1 for r in sub if r.get("top5")) / len(sub),
                "outside_grid_rate": sum(1 for r in sub if r.get("predicted_rank") is None) / len(sub),
            }
        )
    return out
