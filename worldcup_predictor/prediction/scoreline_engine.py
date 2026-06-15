"""Realistic scoreline candidates from intelligence signals."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import ScorelineCandidate


def _poisson_pmf(k: int, lam: float) -> float:
    lam = max(lam, 0.15)
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def _expected_goals_from_report(report: MatchIntelligenceReport) -> tuple[float, float]:
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    engine = ScoringEngine()
    form_home = engine._form_points(report.home_team.form, report.home_team.team_id)
    form_away = engine._form_points(report.away_team.form, report.away_team.team_id)
    form_delta = form_home - form_away
    _, h2h_bias = engine._score_h2h(report.head_to_head, report.home_team.team_id)
    _, inj_bias = engine._score_injuries(report)
    _, odds_bias, _ = engine._score_odds(report.odds)
    home_strength = 1.0 + form_delta * 0.05 + h2h_bias + inj_bias + odds_bias
    away_strength = 1.0 - form_delta * 0.05 - h2h_bias - inj_bias - odds_bias
    return engine._estimate_goals(report, home_strength, away_strength)


def generate_scoreline_candidates(
    report: MatchIntelligenceReport,
    *,
    home_lambda: float | None = None,
    away_lambda: float | None = None,
    top_n: int = 3,
) -> list[ScorelineCandidate]:
    if home_lambda is None or away_lambda is None:
        home_lambda, away_lambda = _expected_goals_from_report(report)

    home_lambda = max(0.35, min(home_lambda, 3.8))
    away_lambda = max(0.35, min(away_lambda, 3.8))

    raw: list[tuple[int, int, float]] = []
    for home in range(0, 6):
        for away in range(0, 6):
            prob = _poisson_pmf(home, home_lambda) * _poisson_pmf(away, away_lambda)
            if prob > 0.001:
                raw.append((home, away, prob))

    raw.sort(key=lambda item: item[2], reverse=True)
    top = raw[:top_n]
    total = sum(p for _, _, p in top) or 1.0
    return [
        ScorelineCandidate(
            home_goals=h,
            away_goals=a,
            probability=round(p / total, 3),
        )
        for h, a, p in top
    ]


def primary_scoreline(candidates: list[ScorelineCandidate]) -> tuple[int, int]:
    if not candidates:
        return 1, 1
    top = candidates[0]
    return top.home_goals, top.away_goals
