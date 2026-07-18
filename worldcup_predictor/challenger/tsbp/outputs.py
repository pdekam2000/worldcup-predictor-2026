"""TSBP_SHADOW labelled score-grid and market outputs."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.challenger.tsbp.constants import BIVARIATE_CORR, MAX_GOALS_GRID, TSBP_DISTRIBUTION, TSBP_LABEL


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def bivariate_goals_to_markets(
    lam_h: float,
    lam_a: float,
    *,
    corr: float = BIVARIATE_CORR,
    max_goals: int = MAX_GOALS_GRID,
    strength_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lam_h = max(0.05, min(6.0, float(lam_h)))
    lam_a = max(0.05, min(6.0, float(lam_a)))
    ph = [_poisson_pmf(i, lam_h) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(j, lam_a) for j in range(max_goals + 1)]
    grid = []
    p_home = p_draw = p_away = 0.0
    p_btts_yes = 0.0
    p_over15 = p_over25 = p_over35 = 0.0
    p_home_over05 = p_away_over05 = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            base = ph[i] * pa[j]
            share = math.exp(-abs(i - j) * corr) * (1.0 + corr if i == j else 1.0 - corr * 0.25)
            p = max(0.0, base * share)
            grid.append({"score": f"{i}-{j}", "probability": p, "home_goals": i, "away_goals": j})
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i >= 1 and j >= 1:
                p_btts_yes += p
            tot = i + j
            if tot >= 2:
                p_over15 += p
            if tot >= 3:
                p_over25 += p
            if tot >= 4:
                p_over35 += p
            if i >= 1:
                p_home_over05 += p
            if j >= 1:
                p_away_over05 += p
    mass = sum(g["probability"] for g in grid) or 1.0
    for g in grid:
        g["probability"] /= mass
    p_home /= mass
    p_draw /= mass
    p_away /= mass
    p_btts_yes /= mass
    p_over15 /= mass
    p_over25 /= mass
    p_over35 /= mass
    p_home_over05 /= mass
    p_away_over05 /= mass
    s_hda = p_home + p_draw + p_away
    if s_hda > 0:
        p_home, p_draw, p_away = p_home / s_hda, p_draw / s_hda, p_away / s_hda
    grid.sort(key=lambda r: -r["probability"])
    top10 = [{"rank": i + 1, "score": g["score"], "probability": round(g["probability"], 6)} for i, g in enumerate(grid[:10])]
    s10 = sum(x["probability"] for x in top10) or 1.0
    ent = -sum((x["probability"] / s10) * math.log(x["probability"] / s10) for x in top10 if x["probability"] > 0)
    meta = strength_meta or {}
    out = {
        "label": TSBP_LABEL,
        "distribution": TSBP_DISTRIBUTION,
        "distribution_family": "TSBP_BIVARIATE_POISSON",
        "expected_home_goals": round(lam_h, 4),
        "expected_away_goals": round(lam_a, 4),
        "expected_total_goals": round(lam_h + lam_a, 4),
        "covariance_dependence_parameter": corr,
        "home_attack_strength": meta.get("home_attack"),
        "away_attack_strength": meta.get("away_attack"),
        "home_defence_strength": meta.get("home_defence"),
        "away_defence_strength": meta.get("away_defence"),
        "league_goal_baseline": meta.get("league_baseline"),
        "home_advantage": meta.get("home_advantage"),
        "hda": {"home": round(p_home, 4), "draw": round(p_draw, 4), "away": round(p_away, 4)},
        "home_probability": round(p_home, 4),
        "draw_probability": round(p_draw, 4),
        "away_probability": round(p_away, 4),
        "decision_1x2": max([("home", p_home), ("draw", p_draw), ("away", p_away)], key=lambda t: t[1])[0],
        "predicted_direction": max([("home", p_home), ("draw", p_draw), ("away", p_away)], key=lambda t: t[1])[0],
        "btts_yes": round(p_btts_yes, 4),
        "btts_no": round(max(0.0, 1.0 - p_btts_yes), 4),
        "btts_selection": "yes" if p_btts_yes >= 0.5 else "no",
        "ou15_over": round(p_over15, 4),
        "ou15_under": round(max(0.0, 1.0 - p_over15), 4),
        "ou25_over": round(p_over25, 4),
        "ou25_under": round(max(0.0, 1.0 - p_over25), 4),
        "ou25_selection": "over_2_5" if p_over25 >= 0.5 else "under_2_5",
        "ou35_over": round(p_over35, 4),
        "ou35_under": round(max(0.0, 1.0 - p_over35), 4),
        "team_total_home_over_0_5": round(p_home_over05, 4),
        "team_total_away_over_0_5": round(p_away_over05, 4),
        "top1_score": top10[0]["score"] if top10 else None,
        "top10": top10,
        "top5": top10[:5],
        "top3_mass": round(sum(x["probability"] for x in top10[:3]), 6),
        "top5_mass": round(sum(x["probability"] for x in top10[:5]), 6),
        "top10_mass": round(sum(x["probability"] for x in top10), 6),
        "entropy": round(ent, 6),
        "score_grid_retained_mass": round(mass / mass, 6),  # post-norm = 1; pre-norm stored below
        "score_grid_pre_norm_mass": round(mass, 6),
        "max_goals": max_goals,
        "corr": corr,
    }
    # stamp every top-level market field as TSBP_SHADOW via nested provenance
    out["field_provenance"] = TSBP_LABEL
    out["not_ecse"] = True
    return out
