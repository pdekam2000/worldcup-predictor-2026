"""Research-only alternative score distributions and tail corrections."""

from __future__ import annotations

import copy
import math
from typing import Any

from worldcup_predictor.research.ecse_lambda_extraction import btts_prob_independent, devig_yes_no
from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    MAX_GOALS,
    OTHER_SCORELINE,
    generate_score_distribution,
    poisson_pmf,
    scoreline_label,
)

METHOD_META: dict[str, str] = {}


def _normalize(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(float(e["probability"]) for e in entries)
    if total <= 0:
        return []
    for e in entries:
        e["probability"] = float(e["probability"]) / total
    entries.sort(key=lambda x: x["probability"], reverse=True)
    for i, e in enumerate(entries, 1):
        e["rank"] = i
    return entries


def _from_grid_probs(grid: dict[tuple[int, int], float], *, max_goals: int = MAX_GOALS) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    mass = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = grid.get((h, a), 0.0)
            mass += p
            entries.append(
                {
                    "scoreline": scoreline_label(h, a),
                    "home_goals": h,
                    "away_goals": a,
                    "probability": p,
                }
            )
    other = max(0.0, 1.0 - mass)
    entries.append(
        {
            "scoreline": OTHER_SCORELINE,
            "home_goals": -1,
            "away_goals": -1,
            "probability": other,
        }
    )
    return _normalize(entries)


def dist_canonical_poisson(lambda_home: float, lambda_away: float) -> list[dict[str, Any]]:
    return generate_score_distribution(lambda_home, lambda_away, use_dixon_coles=False)


def dist_dixon_coles(lambda_home: float, lambda_away: float, *, rho: float = DIXON_COLES_RHO_DEFAULT) -> list[dict[str, Any]]:
    return generate_score_distribution(lambda_home, lambda_away, use_dixon_coles=True, rho=rho)


def dist_bivariate_poisson(
    lambda_home: float,
    lambda_away: float,
    *,
    lambda_shared: float | None = None,
    max_goals: int = MAX_GOALS,
) -> list[dict[str, Any]]:
    """Bivariate Poisson via shared component λ3 (Karlis–Ntzoufras construction)."""
    l1 = max(lambda_home - (lambda_shared or 0), 0.05)
    l2 = max(lambda_away - (lambda_shared or 0), 0.05)
    l3 = max(lambda_shared or min(lambda_home, lambda_away) * 0.12, 0.02)
    grid: dict[tuple[int, int], float] = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = 0.0
            for k in range(min(h, a) + 1):
                p += (
                    math.exp(-(l1 + l2 + l3))
                    * (l1 ** (h - k))
                    * (l2 ** (a - k))
                    * (l3**k)
                    / (math.factorial(h - k) * math.factorial(a - k) * math.factorial(k))
                )
            grid[(h, a)] = max(p, 0.0)
    return _from_grid_probs(grid, max_goals=max_goals)


def dist_negative_binomial(
    lambda_home: float,
    lambda_away: float,
    *,
    dispersion: float = 4.0,
    max_goals: int = MAX_GOALS,
) -> list[dict[str, Any]]:
    """Independent negative-binomial margins for overdispersion."""
    try:
        from scipy.stats import nbinom
    except ImportError:
        return dist_canonical_poisson(lambda_home, lambda_away)

    def nbinom_pmf(k: int, lam: float, r: float) -> float:
        p = r / (r + lam)
        return float(nbinom.pmf(k, r, p))

    r = max(dispersion, 0.5)
    grid: dict[tuple[int, int], float] = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            grid[(h, a)] = nbinom_pmf(h, lambda_home, r) * nbinom_pmf(a, lambda_away, r)
    return _from_grid_probs(grid, max_goals=max_goals)


def dist_tail_temperature(
    lambda_home: float,
    lambda_away: float,
    *,
    temperature: float = 0.88,
) -> list[dict[str, Any]]:
    """Flatten concentration — boost mid/high tail scorelines."""
    base = dist_canonical_poisson(lambda_home, lambda_away)
    boosted: list[dict[str, Any]] = []
    for e in base:
        if e["scoreline"] == OTHER_SCORELINE:
            boosted.append(copy.deepcopy(e))
            continue
        h, a = int(e["home_goals"]), int(e["away_goals"])
        factor = 1.0
        total = h + a
        if total >= 3:
            factor = (1.0 / temperature) ** (total - 2)
        if max(h, a) >= 2 and min(h, a) >= 1:
            factor *= 1.15
        ne = copy.deepcopy(e)
        ne["probability"] = float(e["probability"]) * factor
        boosted.append(ne)
    return _normalize(boosted)


def dist_underdog_floor(
    lambda_home: float,
    lambda_away: float,
    *,
    odds_home: float,
    odds_away: float,
    floor_ratio: float = 0.35,
) -> list[dict[str, Any]]:
    """Raise weaker-side λ when favourite dominance is extreme."""
    lh, la = lambda_home, lambda_away
    if odds_home < odds_away and odds_home < 1.55:
        la = max(la, lh * floor_ratio)
    elif odds_away < odds_home and odds_away < 1.55:
        lh = max(lh, la * floor_ratio)
    return dist_canonical_poisson(lh, la)


def dist_btts_consistency(
    lambda_home: float,
    lambda_away: float,
    *,
    odds_features: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Scale lambdas toward market BTTS when model diverges."""
    lh, la = lambda_home, lambda_away
    if odds_features:
        p_btts = devig_yes_no(odds_features.get("btts_yes_closing"), odds_features.get("btts_no_closing"))
        if p_btts is not None:
            model = btts_prob_independent(lh, la)
            if abs(model - p_btts) > 0.05:
                scale = 1.0 + (p_btts - model) * 0.45
                scale = min(max(scale, 0.80), 1.25)
                lh *= scale
                la *= scale
    return dist_canonical_poisson(lh, la)


def dist_league_variance(
    lambda_home: float,
    lambda_away: float,
    *,
    league_multiplier: float = 1.0,
) -> list[dict[str, Any]]:
    m = max(league_multiplier, 0.75)
    return dist_canonical_poisson(lambda_home * m, lambda_away * m)


def dist_hybrid_tail(
    lambda_home: float,
    lambda_away: float,
    *,
    odds_home: float,
    odds_away: float,
    odds_features: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Chain underdog floor → BTTS consistency → mild tail temperature."""
    lh, la = lambda_home, lambda_away
    if odds_home < odds_away and odds_home < 1.55:
        la = max(la, lh * 0.35)
    elif odds_away < odds_home and odds_away < 1.55:
        lh = max(lh, la * 0.35)
    base = dist_btts_consistency(lh, la, odds_features=odds_features)
    # Temperature flatten on BTTS-adjusted lambdas
    return dist_tail_temperature(lh, la, temperature=0.90)


def prob_map(dist: list[dict[str, Any]]) -> dict[str, float]:
    return {str(e["scoreline"]): float(e["probability"]) for e in dist}


def topn(dist: list[dict[str, Any]], n: int) -> list[str]:
    return [e["scoreline"] for e in dist if e["scoreline"] != OTHER_SCORELINE][:n]


def tail_diagnostics(dist: list[dict[str, Any]]) -> dict[str, float]:
    pm = prob_map(dist)
    away_one = sum(pm.get(f"{h}-1", 0.0) for h in range(8))
    cs_home = sum(pm.get(f"{h}-0", 0.0) for h in range(1, 8))
    btts = sum(p for k, p in pm.items() if "-" in k and all(int(x) > 0 for x in k.split("-", 1)))
    high_tail = sum(
        p for k, p in pm.items() if "-" in k and (sum(int(x) for x in k.split("-")) >= 5 or max(int(x) for x in k.split("-")) >= 3)
    )
    four_plus = sum(
        p for k, p in pm.items() if "-" in k and sum(int(x) for x in k.split("-")) >= 4
    )
    return {
        "clean_sheet_home_mass": round(cs_home, 6),
        "away_exactly_one_mass": round(away_one, 6),
        "btts_mass": round(btts, 6),
        "four_plus_total_mass": round(four_plus, 6),
        "high_score_tail_mass": round(high_tail, 6),
    }


def redistribution_log(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    """Audit trail for probability mass moves."""
    b = prob_map(before)
    a = prob_map(after)
    moves: list[dict[str, Any]] = []
    for line in set(b) | set(a):
        delta = a.get(line, 0.0) - b.get(line, 0.0)
        if abs(delta) >= 1e-6:
            moves.append(
                {
                    "scoreline": line,
                    "delta_probability": round(delta, 6),
                    "reason": reason,
                }
            )
    return moves
