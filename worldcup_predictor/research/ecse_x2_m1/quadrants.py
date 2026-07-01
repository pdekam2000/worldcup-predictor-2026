"""PHASE ECSE-X2-M1 — Quadrant classification and market probability inference."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import (
    OTHER_SCORELINE,
    generate_score_distribution,
    poisson_pmf,
)
from worldcup_predictor.research.ecse_x2_m1.constants import QUADRANTS

PROB_FLOOR = 1e-9


def _clamp01(x: float) -> float:
    return max(PROB_FLOOR, min(1.0 - PROB_FLOOR, x))


def implied_probability(odd: float | None) -> float | None:
    if odd is None or odd <= 1.0:
        return None
    return 1.0 / float(odd)


def devig_pair(a: float | None, b: float | None) -> tuple[float | None, float | None]:
    if a is None or b is None:
        return a, b
    total = a + b
    if total <= 0:
        return None, None
    return a / total, b / total


def classify_score(home_goals: int, away_goals: int) -> frozenset[str]:
    """Map a scoreline to exactly one BTTS×OU quadrant."""
    if home_goals < 0 or away_goals < 0:
        return frozenset()
    btts_yes = home_goals >= 1 and away_goals >= 1
    over_25 = (home_goals + away_goals) >= 3
    if btts_yes and over_25:
        return frozenset({"yes_over"})
    if btts_yes:
        return frozenset({"yes_under"})
    if not over_25:
        return frozenset({"no_under"})
    return frozenset({"no_over"})


def quadrant_probs_joint(p_btts_yes: float, p_over_25: float) -> dict[str, float]:
    """Independent joint probabilities for the four score-worlds."""
    p_btts_yes = _clamp01(p_btts_yes)
    p_over_25 = _clamp01(p_over_25)
    p_btts_no = 1.0 - p_btts_yes
    p_under_25 = 1.0 - p_over_25
    raw = {
        "yes_over": p_btts_yes * p_over_25,
        "yes_under": p_btts_yes * p_under_25,
        "no_under": p_btts_no * p_under_25,
        "no_over": p_btts_no * p_over_25,
    }
    total = sum(raw.values())
    return {k: round(v / total, 8) for k, v in raw.items()}


def dominant_quadrant(q_probs: dict[str, float]) -> str:
    return max(QUADRANTS, key=lambda k: q_probs.get(k, 0.0))


def infer_btts_over_from_lambdas(lambda_home: float, lambda_away: float) -> tuple[float, float]:
    lh = max(float(lambda_home), 1e-9)
    la = max(float(lambda_away), 1e-9)
    p_btts_yes = 1.0 - math.exp(-lh) - math.exp(-la) + math.exp(-(lh + la))
    p_btts_yes = _clamp01(p_btts_yes)

    p_over = 0.0
    max_g = 7
    for h in range(max_g + 1):
        ph = poisson_pmf(h, lh)
        for a in range(max_g + 1):
            if h + a >= 3:
                p_over += ph * poisson_pmf(a, la)
    p_over = _clamp01(p_over)
    return p_btts_yes, p_over


def resolve_market_probs(
    *,
    btts_yes_closing: float | None,
    btts_no_closing: float | None,
    ou_over_25_closing: float | None,
    ou_under_25_closing: float | None,
    lambda_home: float | None,
    lambda_away: float | None,
) -> dict[str, Any]:
    """Infer BTTS / OU probabilities — prematch odds only, never results."""
    p_btts_yes, p_btts_no = devig_pair(
        implied_probability(btts_yes_closing),
        implied_probability(btts_no_closing),
    )
    p_over, p_under = devig_pair(
        implied_probability(ou_over_25_closing),
        implied_probability(ou_under_25_closing),
    )

    source = "odds_closing"
    if p_btts_yes is None or p_over is None:
        if lambda_home is not None and lambda_away is not None:
            lh_yes, lh_over = infer_btts_over_from_lambdas(lambda_home, lambda_away)
            if p_btts_yes is None:
                p_btts_yes = lh_yes
            if p_over is None:
                p_over = lh_over
            source = "lambda_poisson" if source != "odds_closing" else (
                "odds_plus_lambda" if (btts_yes_closing or ou_over_25_closing) else "lambda_poisson"
            )
        else:
            return {
                "ok": False,
                "source": "insufficient",
                "p_btts_yes": None,
                "p_btts_no": None,
                "p_over_25": None,
                "p_under_25": None,
                "quadrant_probs": {},
                "dominant_quadrant": None,
            }

    if p_btts_no is None:
        p_btts_no = 1.0 - float(p_btts_yes)
    if p_under is None:
        p_under = 1.0 - float(p_over)

    p_btts_yes = _clamp01(float(p_btts_yes))
    p_over = _clamp01(float(p_over))
    q_probs = quadrant_probs_joint(p_btts_yes, p_over)

    return {
        "ok": True,
        "source": source,
        "p_btts_yes": round(p_btts_yes, 6),
        "p_btts_no": round(1.0 - p_btts_yes, 6),
        "p_over_25": round(p_over, 6),
        "p_under_25": round(1.0 - p_over, 6),
        "quadrant_probs": q_probs,
        "dominant_quadrant": dominant_quadrant(q_probs),
    }


def scoreline_quadrant_compat(
    home_goals: int,
    away_goals: int,
    scoreline: str,
    q_probs: dict[str, float],
) -> float:
    if scoreline == OTHER_SCORELINE or home_goals < 0 or away_goals < 0:
        return max(q_probs.values()) if q_probs else 0.25
    quads = classify_score(home_goals, away_goals)
    return sum(float(q_probs.get(q, 0.0)) for q in quads)
