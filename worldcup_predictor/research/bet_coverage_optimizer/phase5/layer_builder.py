"""Build Exact3 / Main / Insurance layers from real prematch markets (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.models import ScoringWeights
from worldcup_predictor.research.bet_coverage_optimizer.phase5.constants import RAW_MARKET_SPECS
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import covered_scores_for_market
from worldcup_predictor.research.bet_coverage_optimizer.scoring import (
    compute_coverage_metrics,
    score_candidates,
)


def _fodds(raw: dict[str, Any], key: str) -> float | None:
    try:
        v = float(raw.get(key))
    except (TypeError, ValueError):
        return None
    return v if v > 1.0 else None


def extract_real_market_candidates(
    raw: dict[str, Any],
    *,
    top_n_pairs: list[tuple[str, float]],
    exact3: list[str],
) -> list[dict[str, Any]]:
    """Map real CSV prematch odds into coverage candidates. Never fabricates odds."""
    out: list[dict[str, Any]] = []
    for label, mt, params, odds_key in RAW_MARKET_SPECS:
        odds = _fodds(raw, odds_key)
        if odds is None:
            continue
        covered = covered_scores_for_market(mt, params, [s for s, _ in top_n_pairs])
        if covered is None:
            continue
        metrics = compute_coverage_metrics(
            target_scores=top_n_pairs,
            covered_scores=covered,
            exact_scores=exact3,
            odds=odds,
        )
        out.append(
            {
                "market_label": label,
                "market_family": label.split()[0] if label else mt,
                "market_family_key": mt,
                "market_type": mt,
                "market_parameters": dict(params),
                "odds": odds,
                "odds_source_field": odds_key,
                "odds_lane": "REAL",
                "source_type": "historical_csv_prematch",
                "eligible": True,
                "rejection_reasons": [],
                "odds_freshness_status": "FRESH_ODDS",
                **metrics,
            }
        )
    return score_candidates(out, weights=ScoringWeights(min_odds=1.50), require_fresh=False)


def select_main_and_insurance(
    candidates: list[dict[str, Any]],
    *,
    top_n_pairs: list[tuple[str, float]],
    exact3: list[str],
) -> dict[str, Any]:
    top_map = {s: float(p) for s, p in top_n_pairs}
    exact_set = set(exact3)
    primary = set(exact3)
    main = next((c for c in candidates if c.get("eligible") and c.get("coverage_score") is not None), None)
    main_scores: list[str] = []
    if main:
        main_scores = list(main.get("covered_scores") or [])
        primary.update(main_scores)

    # Insurance: maximize incremental uncovered mass among remaining
    uncovered = [s for s, _ in top_n_pairs if s not in primary]
    uncovered_set = set(uncovered)
    best_ins = None
    best_inc = -1.0
    for c in candidates:
        if main is not None and c.get("market_label") == main.get("market_label"):
            continue
        if not c.get("eligible"):
            continue
        covered = set(c.get("covered_scores") or [])
        new = covered & uncovered_set
        inc = sum(top_map.get(s, 0.0) for s in new)
        overlap = sum(top_map.get(s, 0.0) for s in covered if s in primary)
        primary_mass = sum(top_map.get(s, 0.0) for s in primary) or 1e-12
        overlap_ratio = overlap / primary_mass
        if inc < 0.02:
            continue
        if overlap_ratio > 0.90:
            continue
        if inc > best_inc:
            best_inc = inc
            best_ins = {
                **c,
                "covered_uncovered_scores": sorted(new),
                "incremental_uncovered_probability_mass": round(inc, 8),
                "primary_overlap_ratio": round(overlap_ratio, 8),
            }

    covered_mass = round(sum(top_map.get(s, 0.0) for s in primary), 8)
    ins_scores = list((best_ins or {}).get("covered_uncovered_scores") or [])
    final_primary = set(primary) | set(ins_scores)
    residual = [s for s, _ in top_n_pairs if s not in final_primary]
    residual_mass = round(sum(top_map.get(s, 0.0) for s in residual), 8)
    top_mass = round(sum(p for _, p in top_n_pairs), 8) or 1e-12

    return {
        "exact3": list(exact3),
        "main_coverage": main,
        "main_coverage_scores": main_scores,
        "insurance": best_ins,
        "insurance_scores": ins_scores,
        "primary_covered_scores": sorted(primary),
        "primary_covered_mass": covered_mass,
        "residual_scores": residual,
        "residual_mass": residual_mass,
        "coverage_ratio_primary": round(covered_mass / top_mass, 8),
        "coverage_ratio_with_insurance": round(
            sum(top_map.get(s, 0.0) for s in final_primary) / top_mass, 8
        ),
        "n_markets_available": len(candidates),
        "exact_set_size": len(exact_set),
    }
