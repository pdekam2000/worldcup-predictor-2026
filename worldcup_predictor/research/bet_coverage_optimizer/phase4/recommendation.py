"""Final owner recommendation engine (research-only, no deploy)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import (
    InsuranceCandidate,
    InsuranceTicket,
    UncoveredMassReport,
)
from worldcup_predictor.research.bet_coverage_optimizer.market_semantics import human_label
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation


def _insurance_label(best: InsuranceCandidate | None) -> str | None:
    if best is None:
        return None
    label = str(best.market_label or "").strip()
    if label.lower() in {"yes", "no"} and best.market_type:
        return human_label(best.market_type, dict(best.market_parameters or {}))
    return label or None


def build_final_recommendations(
    recommendations: list[CoverageRecommendation],
    *,
    uncovered_by: dict[int, UncoveredMassReport],
    ranked_by: dict[int, list[InsuranceCandidate]],
    insurance_tickets: list[InsuranceTicket],
    budget: dict[str, Any],
    comparison: dict[str, Any],
    fixture_names: dict[int, str] | None = None,
    historical_replay: dict[str, Any] | None = None,
    real_market_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    names = fixture_names or {}
    per_fixture = []
    main_stake = float(budget.get("stake_per_main_ticket_eur") or budget.get("equal_main_stake_eur") or 0.0)
    for rec in recommendations:
        fid = int(rec.fixture_id)
        u = uncovered_by[fid]
        best = next((c for c in ranked_by.get(fid, []) if c.eligible), None)
        exacts = [e.score for e in rec.selected_exact_scores]
        while len(exacts) < 3:
            exacts.append(None)
        top = float(u.top_n_probability_mass) or 1e-12
        recovered = float(best.incremental_uncovered_probability_mass) if best else 0.0
        final_ratio = min(1.0, (float(u.primary_covered_probability_mass) + recovered) / top)
        residual = max(0.0, 1.0 - final_ratio)
        conf = "HIGH" if final_ratio >= 0.85 else ("MEDIUM" if final_ratio >= 0.70 else "LOW")
        per_fixture.append(
            {
                "fixture_id": fid,
                "fixture_name": names.get(fid, str(fid)),
                "Exact_1": exacts[0],
                "Exact_2": exacts[1],
                "Exact_3": exacts[2],
                "Main_Coverage": (
                    rec.selected_coverage_market.market_label if rec.selected_coverage_market else None
                ),
                "Insurance_Pick": _insurance_label(best),
                "Coverage_pct": round(100.0 * final_ratio, 2),
                "Residual_Risk_pct": round(100.0 * residual, 2),
                "Recommended_stake_main_ticket_eur": main_stake,
                "Recommended_stake_insurance_eur": (
                    float(budget.get("equal_insurance_stake_eur") or 0.0) if best else 0.0
                ),
                "Confidence": conf,
            }
        )

    glob = (comparison or {}).get("global") or {}
    hist_cf = (historical_replay or {}).get("complete_coupon_failure") or {}
    real_sum = (real_market_validation or {}).get("summary") or {}
    warnings: list[str] = []
    if not real_sum.get("priced_coverage_and_insurance_all_real", False):
        warnings.append("Some priced markets are not traced to real bookmaker sources.")
    if real_sum.get("n_synthetic", 0):
        warnings.append("Synthetic/ResearchBook markets detected — see real_market_validation.json.")
    if not hist_cf.get("insurance_reduces_complete_failure"):
        warnings.append("Historical replay did not show complete-failure reduction.")
    warnings.append("Research-only. No profit guarantee. Not deployed.")

    return {
        "research_only": True,
        "owner_only": True,
        "per_fixture": per_fixture,
        "coupon": {
            "Main_tickets": 64,
            "Insurance_tickets": len(insurance_tickets),
            "Budget_eur": float(budget.get("total_budget_eur") or budget.get("configured_total_budget_eur") or 0.0),
            "Allocated_eur": float(budget.get("total_allocated_eur") or 0.0),
            "Expected_coverage_improvement": glob.get("relative_risk_reduction"),
            "Risk_reduction": glob.get("relative_risk_reduction"),
            "modeled_probability_all_main_tickets_lose": glob.get(
                "modeled_probability_all_main_tickets_lose"
            ),
            "modeled_probability_main_and_insurance_both_lose": glob.get(
                "modeled_probability_main_and_insurance_both_lose"
            ),
            "historical_main_all_loss_frequency": hist_cf.get("main_only_all_ticket_loss_frequency"),
            "historical_main_insurance_all_loss_frequency": hist_cf.get(
                "main_plus_insurance_all_ticket_loss_frequency"
            ),
            "Warnings": warnings,
        },
    }
