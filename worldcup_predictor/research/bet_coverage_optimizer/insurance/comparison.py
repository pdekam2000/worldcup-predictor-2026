"""Main vs insurance coverage comparison (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import (
    InsuranceCandidate,
    InsuranceTicket,
    UncoveredMassReport,
)
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation


def compare_main_vs_insurance(
    recommendations: list[CoverageRecommendation],
    *,
    uncovered: dict[int, UncoveredMassReport],
    ranked_candidates: dict[int, list[InsuranceCandidate]],
    insurance_tickets: list[InsuranceTicket],
    n_main_tickets: int = 64,
    budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    per_fixture: dict[str, Any] = {}
    for rec in recommendations:
        fid = int(rec.fixture_id)
        u = uncovered[fid]
        elig = [c for c in ranked_candidates.get(fid, []) if c.eligible]
        best = elig[0] if elig else None
        recovered = float(best.incremental_uncovered_probability_mass) if best else 0.0
        final_mass = round(float(u.primary_covered_probability_mass) + recovered, 8)
        top = float(u.top_n_probability_mass) or 1e-12
        per_fixture[str(fid)] = {
            "primary_covered_mass": u.primary_covered_probability_mass,
            "residual_uncovered_mass": u.primary_uncovered_probability_mass,
            "insurance_recovered_mass": recovered,
            "final_covered_mass": min(final_mass, round(top, 8)),
            "coverage_improvement_pp": round(100.0 * recovered / top, 4),
            "top_insurance_candidate": best.to_dict() if best else None,
            "theoretical_model_coverage": {
                "primary_ratio": u.primary_coverage_ratio,
                "final_ratio": round(min(final_mass, top) / top, 8),
            },
            "realized_monetary_ev": "unknown_due_to_missing_odds"
            if any(t.monetary_ev is None for t in insurance_tickets)
            else "see_tickets",
        }

    # Crude modeled "all main lose": product of (1 - max primary leg mass) — research utility only
    main_lose_probs = []
    for rec in recommendations:
        masses = [float(e.weighted_probability or 0.0) for e in rec.selected_exact_scores]
        if rec.selected_coverage_market:
            masses.append(float(rec.selected_coverage_market.estimated_model_probability or 0.0))
        hit = max(masses) if masses else 0.0
        main_lose_probs.append(max(0.0, 1.0 - min(1.0, hit)))
    p_main_all_lose = 1.0
    for p in main_lose_probs:
        p_main_all_lose *= p

    # With insurance: reduce residual using best recovered masses (independence approx)
    p_both_lose = p_main_all_lose
    for rec in recommendations:
        fid = int(rec.fixture_id)
        best = next((c for c in ranked_candidates.get(fid, []) if c.eligible), None)
        if best:
            p_both_lose *= max(0.0, 1.0 - min(1.0, float(best.model_probability or 0.0)))

    return {
        "research_only": True,
        "owner_only": True,
        "per_fixture": per_fixture,
        "global": {
            "n_main_tickets": int(n_main_tickets),
            "n_insurance_tickets": len(insurance_tickets),
            "total_stake_eur": (budget or {}).get("total_allocated_eur"),
            "modeled_probability_all_main_tickets_lose": round(p_main_all_lose, 8),
            "modeled_probability_main_and_insurance_both_lose": round(p_both_lose, 8),
            "relative_risk_reduction": round(
                (p_main_all_lose - p_both_lose) / p_main_all_lose if p_main_all_lose > 0 else 0.0,
                8,
            ),
            "expected_value_if_odds_complete": "unknown_due_to_missing_odds"
            if any(t.combined_odds is None for t in insurance_tickets)
            else "see_ticket_monetary_ev",
            "probability_mass_utility": round(
                sum(float(t.probability_mass_utility) for t in insurance_tickets), 8
            ),
            "distinction": {
                "theoretical_model_coverage": "ECSE/consensus Top-N mass covered by Exact3+Main[+best Insurance]",
                "realized_monetary_ev": "Only when all ticket legs have real odds; never fabricated",
                "unknown_due_to_missing_odds": "Labeled explicitly when odds incomplete",
            },
        },
    }
