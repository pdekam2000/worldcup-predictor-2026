"""Challenger-only score distributions (independent Poisson, Dixon–Coles, bivariate)."""

from __future__ import annotations

import math
from typing import Any


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _dc_tau(i: int, j: int, lam_h: float, lam_a: float, rho: float) -> float:
    if i == 0 and j == 0:
        return 1.0 - lam_h * lam_a * rho
    if i == 0 and j == 1:
        return 1.0 + lam_h * rho
    if i == 1 and j == 0:
        return 1.0 + lam_a * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def goals_to_markets(
    lam_h: float,
    lam_a: float,
    *,
    max_goals: int = 7,
    family: str = "independent_poisson",
    rho: float = -0.05,
    corr: float = 0.05,
) -> dict[str, Any]:
    lam_h = max(0.05, min(6.0, float(lam_h)))
    lam_a = max(0.05, min(6.0, float(lam_a)))
    ph = [_poisson_pmf(i, lam_h) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(j, lam_a) for j in range(max_goals + 1)]
    grid = []
    p_home = p_draw = p_away = 0.0
    p_btts_yes = 0.0
    p_over = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            if family == "dixon_coles":
                p = ph[i] * pa[j] * max(0.0, _dc_tau(i, j, lam_h, lam_a, rho))
            elif family == "bivariate_poisson":
                # Lightweight correlation tilt via shared factor on low-score cells
                base = ph[i] * pa[j]
                share = math.exp(-abs(i - j) * corr) * (1.0 + corr if i == j else 1.0 - corr * 0.25)
                p = max(0.0, base * share)
            else:
                p = ph[i] * pa[j]
            grid.append({"score": f"{i}-{j}", "probability": p, "home_goals": i, "away_goals": j})
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i >= 1 and j >= 1:
                p_btts_yes += p
            if i + j >= 3:
                p_over += p
    mass = sum(g["probability"] for g in grid) or 1.0
    for g in grid:
        g["probability"] /= mass
    p_home /= mass
    p_draw /= mass
    p_away /= mass
    p_btts_yes /= mass
    p_over /= mass
    s_hda = p_home + p_draw + p_away
    if s_hda > 0:
        p_home, p_draw, p_away = p_home / s_hda, p_draw / s_hda, p_away / s_hda
    grid.sort(key=lambda r: -r["probability"])
    top10 = [{"rank": i + 1, "score": g["score"], "probability": round(g["probability"], 6)} for i, g in enumerate(grid[:10])]
    return {
        "expected_home_goals": round(lam_h, 4),
        "expected_away_goals": round(lam_a, 4),
        "hda": {"home": round(p_home, 4), "draw": round(p_draw, 4), "away": round(p_away, 4)},
        "decision_1x2": max([("home", p_home), ("draw", p_draw), ("away", p_away)], key=lambda t: t[1])[0],
        "btts_yes": round(p_btts_yes, 4),
        "btts_no": round(max(0.0, 1.0 - p_btts_yes), 4),
        "btts_selection": "yes" if p_btts_yes >= 0.5 else "no",
        "ou25_over": round(p_over, 4),
        "ou25_under": round(max(0.0, 1.0 - p_over), 4),
        "ou25_selection": "over_2_5" if p_over >= 0.5 else "under_2_5",
        "top1_score": top10[0]["score"] if top10 else None,
        "top10": top10,
        "top5": top10[:5],
        "top3_mass": round(sum(x["probability"] for x in top10[:3]), 6),
        "top5_mass": round(sum(x["probability"] for x in top10[:5]), 6),
        "grid_mass_pre_norm": round(mass, 6),
        "distribution_family": f"GBGM_{family.upper()}",
        "max_goals": max_goals,
        "rho": rho if family == "dixon_coles" else None,
        "corr": corr if family == "bivariate_poisson" else None,
    }
