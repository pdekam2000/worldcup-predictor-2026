"""Configurable pair scoring — pair_score is NOT a probability."""

from __future__ import annotations

from typing import Any


DEFAULT_WEIGHTS = {
    "top10_covered_mass": 0.15,
    "profitable_top10_mass": 0.30,
    "incremental_mass": 0.10,
    "expected_return": 0.20,
    "estimated_edge": 0.10,
    "worst_case_loss_penalty": 0.05,
    "redundancy_penalty": 0.05,
    "concentration_penalty": 0.05,
}


def score_market_pair(features: dict[str, Any], weights: dict[str, float] | None = None) -> dict[str, Any]:
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items()})

    covered = float(features.get("covered_top10_probability_mass") or 0.0)
    profitable = float(features.get("profitable_top10_mass") or 0.0)
    incremental = float(features.get("incremental_uncovered_mass") or 0.0)
    expected = float(features.get("modeled_expected_return") or 0.0)
    edge = float(features.get("estimated_edge") or 0.0)
    worst = float(features.get("worst_case_top10_loss") or 0.0)
    redundancy = float(features.get("market_redundancy") or 0.0)
    concentration = float(features.get("concentration") or 0.0)

    # Normalize expected return roughly into [0,1] via tanh-ish clip
    exp_term = max(-1.0, min(1.0, expected / max(1.0, float(features.get("total_stake") or 25.0))))
    edge_term = max(-1.0, min(1.0, edge))
    worst_pen = abs(min(0.0, worst)) / max(1.0, float(features.get("total_stake") or 25.0))

    pair_score = (
        w["top10_covered_mass"] * covered
        + w["profitable_top10_mass"] * profitable
        + w["incremental_mass"] * incremental
        + w["expected_return"] * (0.5 + 0.5 * exp_term)
        + w["estimated_edge"] * (0.5 + 0.5 * edge_term)
        - w["worst_case_loss_penalty"] * worst_pen
        - w["redundancy_penalty"] * redundancy
        - w["concentration_penalty"] * concentration
    )
    return {
        "pair_score": round(float(pair_score), 8),
        "pair_score_is_probability": False,
        "components": {
            "covered": covered,
            "profitable": profitable,
            "incremental": incremental,
            "expected_return_term": exp_term,
            "edge_term": edge_term,
            "worst_penalty": worst_pen,
            "redundancy": redundancy,
            "concentration": concentration,
        },
        "weights": w,
    }
