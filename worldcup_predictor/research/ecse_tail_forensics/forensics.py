"""Forensic case analysis for ECSE tail failures."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_lambda_extraction import btts_prob_independent, devig_yes_no
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.ecse_tail_forensics.distributions import (
    prob_map,
    tail_diagnostics,
    topn,
)


def analyze_distribution(
    *,
    lambda_home: float,
    lambda_away: float,
    actual_score: str | None = None,
    label: str = "",
    odds_features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dist = generate_score_distribution(lambda_home, lambda_away)
    pm = prob_map(dist)
    top10 = topn(dist, 10)
    top5 = topn(dist, 5)
    away_one_mass = sum(pm.get(f"{h}-1", 0.0) for h in range(8))
    halmstad_zero = pm.get("0-0", 0.0)  # placeholder for away 0 - compute P(away=0)
    away_zero = sum(pm.get(f"{h}-0", 0.0) for h in range(8))
    btts_model = btts_prob_independent(lambda_home, lambda_away)
    p_btts = None
    if odds_features:
        p_btts = devig_yes_no(odds_features.get("btts_yes_closing"), odds_features.get("btts_no_closing"))
    return {
        "label": label,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "total_lambda": round(lambda_home + lambda_away, 4),
        "canonical_top5": top5,
        "canonical_top10": top10,
        "prob_actual": pm.get(actual_score, 0.0) if actual_score else None,
        "actual_rank": next((i + 1 for i, s in enumerate(topn(dist, 65)) if s == actual_score), 999) if actual_score else None,
        "in_top10": actual_score in top10 if actual_score else None,
        "tail_diagnostics": tail_diagnostics(dist),
        "prob_away_scores_0": round(away_zero, 6),
        "prob_away_scores_1": round(away_one_mass, 6),
        "rank_2_1": pm.get("2-1", 0.0),
        "rank_3_1": pm.get("3-1", 0.0),
        "prob_3_2": pm.get("3-2", 0.0),
        "model_btts": round(btts_model, 4),
        "market_btts": round(p_btts, 4) if p_btts is not None else None,
        "all_top5_clean_sheet": all(s.endswith("-0") for s in top5),
    }


def build_forensic_cases() -> list[dict[str, Any]]:
    cases = [
        analyze_distribution(
            lambda_home=2.8,
            lambda_away=0.5,
            actual_score=None,
            label="Djurgardens IF vs Halmstad (fixture 1494202)",
        ),
        analyze_distribution(
            lambda_home=1.4,
            lambda_away=1.6,
            actual_score="3-2",
            label="KA Akureyri vs IA Akranes (fixture 1508804)",
        ),
    ]
    return cases


def build_casebook_from_misses(miss_samples: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    book: list[dict[str, Any]] = []
    for bucket, samples in miss_samples.items():
        for s in samples:
            book.append({"bucket": bucket, **s})
    return book[:25]
