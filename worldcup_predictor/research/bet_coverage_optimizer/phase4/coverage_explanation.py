"""Per-fixture coverage explanation with concrete scorelines (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import (
    InsuranceCandidate,
    UncoveredMassReport,
)
from worldcup_predictor.research.bet_coverage_optimizer.insurance.uncovered_mass import (
    primary_covered_score_set,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.bet_coverage_optimizer.score_mapping import covered_scores_for_market


def explain_fixture_coverage(
    rec: CoverageRecommendation,
    *,
    uncovered: UncoveredMassReport,
    insurance: InsuranceCandidate | None,
    fixture_name: str | None = None,
) -> dict[str, Any]:
    top_map = {s.score: float(s.probability or 0.0) for s in rec.top_n_scores_list}
    primary_exact = [e.score for e in rec.selected_exact_scores]
    main_cov_scores = list(
        (rec.selected_coverage_market.covered_scores if rec.selected_coverage_market else []) or []
    )
    primary = primary_covered_score_set(rec)
    already = sorted(primary)

    insurance_adds: list[str] = []
    insurance_new_mass = 0.0
    if insurance is not None:
        insurance_adds = sorted(str(s) for s in (insurance.covered_uncovered_scores or []))
        insurance_new_mass = float(insurance.incremental_uncovered_probability_mass or 0.0)

    residual_scores = sorted(s for s in top_map if s not in primary and s not in set(insurance_adds))
    residual_mass = round(sum(top_map[s] for s in residual_scores), 8)
    primary_mass = float(uncovered.primary_covered_probability_mass)
    after_mass = round(min(primary_mass + insurance_new_mass, float(uncovered.top_n_probability_mass)), 8)
    top_mass = float(uncovered.top_n_probability_mass) or 1e-12

    return {
        "fixture_id": int(rec.fixture_id),
        "fixture_name": fixture_name or str(rec.fixture_id),
        "primary_selections_cover": {
            "exact_scores": primary_exact,
            "main_coverage_market": (
                rec.selected_coverage_market.market_label if rec.selected_coverage_market else None
            ),
            "main_coverage_scores": main_cov_scores,
            "all_primary_scorelines": already,
            "primary_covered_probability_mass": primary_mass,
        },
        "insurance_covers": {
            "market": insurance.market_label if insurance else None,
            "market_key": insurance.market_key if insurance else None,
            "scorelines_added": insurance_adds,
            "incremental_uncovered_probability_mass": insurance_new_mass,
        },
        "new_covered_scores": insurance_adds,
        "already_covered_scores": already,
        "residual_uncovered_scores": residual_scores,
        "residual_probability_mass": residual_mass,
        "coverage_increase": {
            "absolute_mass": round(insurance_new_mass, 8),
            "percentage_points": round(100.0 * insurance_new_mass / top_mass, 4),
            "primary_ratio": round(primary_mass / top_mass, 8),
            "final_ratio": round(after_mass / top_mass, 8),
        },
        "scoreline_narrative": {
            "Primary": primary_exact + [s for s in main_cov_scores if s not in primary_exact],
            "Insurance_adds": insurance_adds,
            "Not_covered": residual_scores,
        },
    }


def explain_all_fixtures(
    recommendations: list[CoverageRecommendation],
    *,
    uncovered_by: dict[int, UncoveredMassReport],
    ranked_by: dict[int, list[InsuranceCandidate]],
    fixture_names: dict[int, str] | None = None,
) -> dict[str, Any]:
    names = fixture_names or {}
    per: dict[str, Any] = {}
    for rec in recommendations:
        fid = int(rec.fixture_id)
        best = next((c for c in ranked_by.get(fid, []) if c.eligible), None)
        per[str(fid)] = explain_fixture_coverage(
            rec,
            uncovered=uncovered_by[fid],
            insurance=best,
            fixture_name=names.get(fid),
        )
    return {"research_only": True, "fixtures": per}


def alternative_market_scorelines(
    *,
    market_type: str,
    market_parameters: dict[str, Any],
    top_n_scores: list[str],
) -> list[str]:
    covered = covered_scores_for_market(market_type, market_parameters, top_n_scores)
    return sorted(covered or [])
