"""Portfolio risk summary (research-only)."""

from __future__ import annotations

from typing import Any


def compute_portfolio_risk(
    *,
    allocation: dict[str, Any],
    selected: list[dict[str, Any]],
    fixtures_by_id: dict[int, dict[str, Any]],
    diversification: dict[str, Any],
) -> dict[str, Any]:
    stakes = [float(a.get("stake_eur") or 0.0) for a in (allocation.get("allocations") or [])]
    total = sum(stakes)
    if total <= 0:
        return {
            "research_only": True,
            "maximum_loss_eur": 0.0,
            "capital_at_risk_eur": 0.0,
            "expected_drawdown_proxy": 0.0,
            "concentration": 0.0,
            "diversification_score": diversification.get("diversification_score"),
            "worst_case_scenario": "No capital allocated.",
            "best_case_scenario": "No capital allocated.",
        }

    # Concentration HHI
    shares = [s / total for s in stakes]
    hhi = sum(x * x for x in shares)
    max_stake = max(stakes)

    # Best/worst case using odds when present
    best = 0.0
    for a in allocation.get("allocations") or []:
        fx = fixtures_by_id.get(int(a["fixture_id"])) or {}
        odd = fx.get("insurance_odds") or fx.get("odds_home") or 2.0
        try:
            odd_f = float(odd)
        except (TypeError, ValueError):
            odd_f = 2.0
        best += float(a["stake_eur"]) * max(0.0, odd_f - 1.0)

    residual = [
        float((score_row.get("residual_risk") or 0.0))
        for score_row in selected
    ]
    mean_res = sum(residual) / len(residual) if residual else 0.5
    expected_dd = round(total * (0.35 + 0.45 * (mean_res / 100.0)), 4)

    return {
        "research_only": True,
        "maximum_loss_eur": round(total, 2),
        "capital_at_risk_eur": round(total, 2),
        "expected_drawdown_proxy": expected_dd,
        "concentration_hhi": round(hhi, 6),
        "largest_position_eur": round(max_stake, 2),
        "diversification_score": diversification.get("diversification_score"),
        "mean_pairwise_correlation": diversification.get("mean_pairwise_correlation"),
        "worst_case_scenario": f"All selected coupons lose — lose €{round(total, 2)}.",
        "best_case_scenario": f"All selected win at attached odds — approx profit €{round(best, 2)}.",
        "warning": "Scenarios are research proxies, not forecasts.",
    }
