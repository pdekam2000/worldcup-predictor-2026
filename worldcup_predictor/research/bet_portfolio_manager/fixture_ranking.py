"""Fixture ranking for portfolio capital priority (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.constants import MIN_FIXTURE_SCORE_TO_BET


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def score_fixture(
    fx: dict[str, Any],
    *,
    league_reliability: dict[str, float] | None = None,
) -> dict[str, Any]:
    lr = (league_reliability or {}).get(str(fx.get("league") or ""), 0.55)
    conf = _clamp01(float(fx.get("confidence") or 0.0))
    # entropy typically ~1.5–3.5 for score distributions
    ent = float(fx.get("entropy") or 0.0)
    low_ent = _clamp01(1.0 - (ent - 1.5) / 2.5) if ent else 0.5
    cov = _clamp01(float(fx.get("coverage_mass") or 0.0))
    residual = _clamp01(float(fx.get("residual_risk") or 0.0))
    low_res = _clamp01(1.0 - residual)
    ins = _clamp01(float(fx.get("insurance_contribution") or 0.0) / 0.15)
    bal = _clamp01(float(fx.get("odds_balance") or 0.0))
    div = _clamp01(len(fx.get("market_tags") or []) / 3.0)

    investment_priority = round(
        100.0
        * (
            0.22 * conf
            + 0.16 * low_ent
            + 0.16 * cov
            + 0.14 * low_res
            + 0.10 * ins
            + 0.08 * bal
            + 0.06 * div
            + 0.08 * _clamp01(lr)
        ),
        4,
    )
    uncertainty = round(100.0 * (0.5 * (1.0 - low_ent) + 0.5 * residual), 4)
    insurance_dependence = round(100.0 * _clamp01(float(fx.get("insurance_contribution") or 0.0) / max(1e-6, cov or 1e-6)), 4)
    expected_contribution = round(investment_priority * (0.5 + 0.5 * cov), 4)
    diversification_value = round(100.0 * div, 4)

    return {
        "fixture_id": fx["fixture_id"],
        "match_name": fx.get("match_name"),
        "league": fx.get("league"),
        "investment_priority": investment_priority,
        "confidence": round(100.0 * conf, 4),
        "uncertainty": uncertainty,
        "diversification_value": diversification_value,
        "expected_contribution": expected_contribution,
        "historical_reliability": round(100.0 * _clamp01(lr), 4),
        "insurance_dependence": insurance_dependence,
        "residual_risk": round(100.0 * residual, 4),
        "eligible_for_capital": investment_priority >= MIN_FIXTURE_SCORE_TO_BET,
    }


def rank_fixtures(
    fixtures: list[dict[str, Any]],
    *,
    league_reliability: dict[str, float] | None = None,
) -> dict[str, Any]:
    rows = [score_fixture(fx, league_reliability=league_reliability) for fx in fixtures]
    rows.sort(
        key=lambda r: (
            -float(r["investment_priority"]),
            -float(r["expected_contribution"]),
            int(r["fixture_id"]),
        )
    )
    for i, r in enumerate(rows, start=1):
        r["portfolio_rank"] = i
    return {
        "research_only": True,
        "n_fixtures": len(rows),
        "rankings": rows,
        "n_eligible": sum(1 for r in rows if r["eligible_for_capital"]),
    }
