"""Additional shadow-only score distributions for high-score tail research."""

from __future__ import annotations

import math
from typing import Any, Callable

from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    MAX_GOALS,
    OTHER_SCORELINE,
    dixon_coles_tau,
    generate_score_distribution,
    poisson_pmf,
    scoreline_label,
)
from worldcup_predictor.research.ecse_tail_forensics.distributions import (
    _from_grid_probs,
    _normalize,
    dist_canonical_poisson,
    dist_dixon_coles,
    dist_negative_binomial,
    dist_bivariate_poisson,
    topn,
    prob_map,
)


def dynamic_max_goals(lambda_home: float, lambda_away: float) -> int:
    total = float(lambda_home) + float(lambda_away)
    if total < 2.0:
        return 6
    if total < 2.8:
        return 7
    if total < 3.6:
        return 8
    if total < 4.5:
        return 10
    return 12


def dist_dynamic_grid(lambda_home: float, lambda_away: float) -> list[dict[str, Any]]:
    mg = dynamic_max_goals(lambda_home, lambda_away)
    return generate_score_distribution(lambda_home, lambda_away, max_goals=mg, use_dixon_coles=False)


def dist_residual_proportional(lambda_home: float, lambda_away: float, *, base_max: int = 7) -> list[dict[str, Any]]:
    """Expand grid so residual OTHER mass is redistributed onto higher scores proportionally to Poisson density."""
    mg = max(base_max, dynamic_max_goals(lambda_home, lambda_away) + 2)
    return generate_score_distribution(lambda_home, lambda_away, max_goals=mg, use_dixon_coles=False)


def dist_dc_dynamic(lambda_home: float, lambda_away: float, *, rho: float = DIXON_COLES_RHO_DEFAULT) -> list[dict[str, Any]]:
    mg = dynamic_max_goals(lambda_home, lambda_away)
    return generate_score_distribution(lambda_home, lambda_away, max_goals=mg, use_dixon_coles=True, rho=rho)


def dist_nb_dynamic(lambda_home: float, lambda_away: float, *, dispersion: float = 3.5) -> list[dict[str, Any]]:
    mg = dynamic_max_goals(lambda_home, lambda_away)
    return dist_negative_binomial(lambda_home, lambda_away, dispersion=dispersion, max_goals=mg)


def dist_mixture_regimes(
    lambda_home: float,
    lambda_away: float,
    *,
    w_low: float = 0.25,
    w_mid: float = 0.50,
    w_high: float = 0.25,
) -> list[dict[str, Any]]:
    """Three-regime Poisson mixture with prematch-only λ scales."""
    ws = [max(w_low, 0), max(w_mid, 0), max(w_high, 0)]
    s = sum(ws) or 1.0
    ws = [w / s for w in ws]
    scales = (0.70, 1.0, 1.45)
    mg = dynamic_max_goals(lambda_home * 1.45, lambda_away * 1.45)
    grid: dict[tuple[int, int], float] = {}
    for w, sc in zip(ws, scales):
        lh, la = max(0.05, lambda_home * sc), max(0.05, lambda_away * sc)
        for h in range(mg + 1):
            for a in range(mg + 1):
                grid[(h, a)] = grid.get((h, a), 0.0) + w * poisson_pmf(h, lh) * poisson_pmf(a, la)
    return _from_grid_probs(grid, max_goals=mg)


def dist_hurdle_hybrid(
    lambda_home: float,
    lambda_away: float,
    *,
    rho: float = DIXON_COLES_RHO_DEFAULT,
    high_weight: float = 0.35,
) -> list[dict[str, Any]]:
    """Blend Dixon–Coles (low/mid) with over-dispersed NB (high)."""
    dc = prob_map(dist_dixon_coles(lambda_home, lambda_away, rho=rho))
    nb = prob_map(dist_nb_dynamic(lambda_home, lambda_away))
    keys = set(dc) | set(nb)
    keys.discard(OTHER_SCORELINE)
    blended: dict[str, float] = {}
    for k in keys:
        h, a = map(int, k.split("-"))
        tot = h + a
        w_high = high_weight if tot >= 4 else 0.15 if tot == 3 else 0.05
        blended[k] = (1 - w_high) * dc.get(k, 0.0) + w_high * nb.get(k, 0.0)
    entries = []
    mass = 0.0
    for sc, p in blended.items():
        h, a = map(int, sc.split("-"))
        entries.append({"scoreline": sc, "home_goals": h, "away_goals": a, "probability": p})
        mass += p
    entries.append(
        {"scoreline": OTHER_SCORELINE, "home_goals": -1, "away_goals": -1, "probability": max(0.0, 1.0 - mass)}
    )
    return _normalize(entries)


def dist_market_total_tail(
    lambda_home: float,
    lambda_away: float,
    *,
    ou_prediction: str | None,
    scale_over: float = 1.12,
    scale_under: float = 0.92,
) -> list[dict[str, Any]]:
    """Scale lambdas using O/U direction only (no invented odds)."""
    lh, la = lambda_home, lambda_away
    ou = str(ou_prediction or "").lower()
    if "over" in ou:
        lh *= scale_over
        la *= scale_over
    elif "under" in ou:
        lh *= scale_under
        la *= scale_under
    return dist_nb_dynamic(lh, la)


def dist_favorite_blowout(
    lambda_home: float,
    lambda_away: float,
    *,
    wde_home: float | None,
    wde_away: float | None,
) -> list[dict[str, Any]]:
    """If strong favorite implied by WDE probs, inflate favorite λ slightly."""
    lh, la = lambda_home, lambda_away
    if wde_home is not None and wde_away is not None:
        hp = wde_home / 100.0 if wde_home > 1.5 else wde_home
        ap = wde_away / 100.0 if wde_away > 1.5 else wde_away
        if hp >= 0.70 and hp - ap >= 0.40:
            lh *= 1.18
        elif ap >= 0.70 and ap - hp >= 0.40:
            la *= 1.18
    return dist_nb_dynamic(lh, la)


def dist_underdog_scoring_tail(
    lambda_home: float,
    lambda_away: float,
    *,
    wde_home: float | None,
    wde_away: float | None,
    floor_ratio: float = 0.40,
) -> list[dict[str, Any]]:
    lh, la = lambda_home, lambda_away
    if wde_home is not None and wde_away is not None:
        hp = wde_home / 100.0 if wde_home > 1.5 else wde_home
        ap = wde_away / 100.0 if wde_away > 1.5 else wde_away
        if hp >= 0.65:
            la = max(la, lh * floor_ratio)
        elif ap >= 0.65:
            lh = max(lh, la * floor_ratio)
    return dist_nb_dynamic(lh, la)


def dist_ensemble_tail(
    lambda_home: float,
    lambda_away: float,
    *,
    ou_prediction: str | None = None,
    wde_home: float | None = None,
    wde_away: float | None = None,
) -> list[dict[str, Any]]:
    """Average of DC-dynamic, NB-dynamic, hurdle, market-tail."""
    parts = [
        dist_dc_dynamic(lambda_home, lambda_away),
        dist_nb_dynamic(lambda_home, lambda_away),
        dist_hurdle_hybrid(lambda_home, lambda_away),
        dist_market_total_tail(lambda_home, lambda_away, ou_prediction=ou_prediction),
        dist_favorite_blowout(lambda_home, lambda_away, wde_home=wde_home, wde_away=wde_away),
    ]
    maps = [prob_map(p) for p in parts]
    keys = set().union(*(m.keys() for m in maps))
    keys.discard(OTHER_SCORELINE)
    blended = {k: sum(m.get(k, 0.0) for m in maps) / len(maps) for k in keys}
    entries = []
    mass = 0.0
    for sc, p in blended.items():
        h, a = map(int, sc.split("-"))
        entries.append({"scoreline": sc, "home_goals": h, "away_goals": a, "probability": p})
        mass += p
    entries.append(
        {"scoreline": OTHER_SCORELINE, "home_goals": -1, "away_goals": -1, "probability": max(0.0, 1.0 - mass)}
    )
    return _normalize(entries)


def dist_low_score_specialist(lambda_home: float, lambda_away: float) -> list[dict[str, Any]]:
    """CHALLENGER L — Dixon–Coles on dynamic grid."""
    return dist_dc_dynamic(lambda_home, lambda_away)


def dist_high_score_specialist(
    lambda_home: float,
    lambda_away: float,
    *,
    ou_prediction: str | None = None,
    wde_home: float | None = None,
    wde_away: float | None = None,
) -> list[dict[str, Any]]:
    """CHALLENGER H — ensemble of over-dispersed / market / blowout tails."""
    return dist_ensemble_tail(
        lambda_home,
        lambda_away,
        ou_prediction=ou_prediction,
        wde_home=wde_home,
        wde_away=wde_away,
    )


def tail_mass(dist: list[dict[str, Any]], min_total: int = 4) -> float:
    s = 0.0
    for e in dist:
        if e["scoreline"] == OTHER_SCORELINE:
            continue
        if int(e["home_goals"]) + int(e["away_goals"]) >= min_total:
            s += float(e["probability"])
    return s


def other_mass(dist: list[dict[str, Any]]) -> float:
    for e in dist:
        if e["scoreline"] == OTHER_SCORELINE:
            return float(e["probability"])
    return 0.0


CHALLENGER_FNS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "canonical_poisson_7": dist_canonical_poisson,
    "H1_dynamic_grid": dist_dynamic_grid,
    "H2_residual_expand": dist_residual_proportional,
    "H3_negative_binomial": dist_nb_dynamic,
    "H4_hurdle_hybrid": dist_hurdle_hybrid,
    "H5_mixture_regimes": dist_mixture_regimes,
    "G3_dixon_coles": dist_dixon_coles,
    "L_low_score_specialist": dist_low_score_specialist,
    "H_high_score_specialist": dist_high_score_specialist,
    "H6_market_total": dist_market_total_tail,
    "H8_favorite_blowout": dist_favorite_blowout,
    "H9_underdog_tail": dist_underdog_scoring_tail,
    "H10_ensemble": dist_ensemble_tail,
}
