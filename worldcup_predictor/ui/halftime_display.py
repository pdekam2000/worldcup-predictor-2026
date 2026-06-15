"""Halftime goal display helpers."""

from __future__ import annotations

import math

from worldcup_predictor.domain.prediction import MatchPrediction


def _poisson_prob(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def halftime_total_outcomes(expected_goals: float, limit: int = 4) -> list[tuple[str, float]]:
    """Most likely first-half total goal counts with probabilities."""
    rows: list[tuple[str, float]] = []
    for k in range(limit):
        label = f"{k} goal{'s' if k != 1 else ''}" if k < 3 else "3+ goals"
        rows.append((label, _poisson_prob(expected_goals, k)))
    if limit > 3:
        tail = max(0.0, 1.0 - sum(p for _, p in rows[:-1]))
        rows[-1] = ("3+ goals", tail)
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def halftime_scoreline_outcomes(prediction: MatchPrediction, limit: int = 3) -> list[tuple[str, float | None]]:
    """Likely first-half scorelines — percentages when estimable."""
    expected = prediction.halftime.estimated_total_goals
    if prediction.scoreline:
        home_share = prediction.scoreline.home_goals / max(
            prediction.scoreline.home_goals + prediction.scoreline.away_goals, 0.01
        )
    else:
        home_share = 0.5

    lam_home = expected * home_share
    lam_away = expected * (1.0 - home_share)
    candidates = [
        (0, 0),
        (1, 0),
        (0, 1),
        (1, 1),
        (2, 0),
        (0, 2),
    ]
    scored: list[tuple[str, float]] = []
    for h, a in candidates:
        prob = _poisson_prob(lam_home, h) * _poisson_prob(lam_away, a)
        scored.append((f"{h}-{a}", prob))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [(label, prob) for label, prob in scored[:limit]]
