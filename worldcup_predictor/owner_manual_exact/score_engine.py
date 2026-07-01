"""Poisson exact-score generation from market odds (fallback / blend)."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.wde_shadow_historical.helpers import implied_probs


def _poisson_pmf(k: int, lam: float) -> float:
    lam = max(lam, 0.12)
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _scoreline_str(h: int, a: int) -> str:
    return f"{h}-{a}"


def estimate_lambdas_from_1x2(p_home: float, p_draw: float, p_away: float) -> tuple[float, float]:
    """Heuristic expected goals from normalized 1X2 implied probabilities."""
    p_home = max(p_home, 0.05)
    p_draw = max(p_draw, 0.05)
    p_away = max(p_away, 0.05)
    home_strength = p_home / (p_home + p_away + 1e-9)
    decisiveness = 1.0 - min(p_draw, 0.32) * 1.8
    total = 2.05 + decisiveness * 0.75 + abs(home_strength - 0.5) * 1.4
    home_lambda = total * (0.38 + home_strength * 0.24)
    away_lambda = max(0.25, total - home_lambda)
    if home_strength > 0.62:
        home_lambda *= 1.2
        away_lambda *= 0.75
    elif home_strength < 0.38:
        away_lambda *= 1.2
        home_lambda *= 0.75
    return round(home_lambda, 3), round(away_lambda, 3)


def poisson_score_distribution(
    home_lambda: float,
    away_lambda: float,
    *,
    max_goals: int = 5,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    raw: list[tuple[int, int, float]] = []
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson_pmf(h, home_lambda) * _poisson_pmf(a, away_lambda)
            if p > 1e-5:
                raw.append((h, a, p))
    raw.sort(key=lambda x: x[2], reverse=True)
    top = raw[:top_n]
    total = sum(p for _, _, p in top) or 1.0
    return [
        {"scoreline": _scoreline_str(h, a), "home_goals": h, "away_goals": a, "probability": round(p / total, 4)}
        for h, a, p in top
    ]


def markets_from_odds(odds_1x2: dict[str, float], btts_odds: dict[str, float]) -> dict[str, Any]:
    ip = implied_probs(
        {
            "home": odds_1x2.get("home"),
            "draw": odds_1x2.get("draw"),
            "away": odds_1x2.get("away"),
        }
    )
    p_home = float(ip.get("home") or 0.33)
    p_draw = float(ip.get("draw") or 0.33)
    p_away = float(ip.get("away") or 0.33)

    btts_ip = implied_probs({"yes": btts_odds.get("yes"), "no": btts_odds.get("no")})
    p_btts_yes = float(btts_ip.get("yes") or 0.5)

    pick_1x2 = max({"home_win": p_home, "draw": p_draw, "away_win": p_away}, key=lambda k: {"home_win": p_home, "draw": p_draw, "away_win": p_away}[k])
    hl, al = estimate_lambdas_from_1x2(p_home, p_draw, p_away)
    scores = poisson_score_distribution(hl, al, top_n=5)

    ou_over = 0.0
    for s in poisson_score_distribution(hl, al, top_n=36):
        if s["home_goals"] + s["away_goals"] > 2:
            ou_over += s["probability"]
    ou_pick = "over_2_5" if ou_over >= 0.5 else "under_2_5"
    btts_pick = "yes" if p_btts_yes >= 0.5 else "no"

    return {
        "implied_prob_home": round(p_home, 4),
        "implied_prob_draw": round(p_draw, 4),
        "implied_prob_away": round(p_away, 4),
        "implied_prob_btts_yes": round(p_btts_yes, 4),
        "pick_1x2": pick_1x2,
        "pick_btts": btts_pick,
        "pick_ou25": ou_pick,
        "home_lambda": hl,
        "away_lambda": al,
        "top_scores": scores,
        "odds_derived": True,
    }
