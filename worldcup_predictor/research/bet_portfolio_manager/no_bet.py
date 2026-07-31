"""No-bet / day action engine (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.constants import MIN_FIXTURE_SCORE_TO_BET


def decide_no_bet(
    daily: dict[str, Any],
    rankings: dict[str, Any],
    diversification: dict[str, Any],
) -> dict[str, Any]:
    """
    Map day quality → BET | SMALL BET | WATCH | SKIP.
    May tighten the daily recommendation using hard vetoes.
    """
    base = str(daily.get("recommendation") or "SKIP")
    score = float(daily.get("daily_portfolio_score") or 0.0)
    reasons: list[str] = list(daily.get("reasoning") or [])
    vetoes: list[str] = []

    comps = daily.get("components") or {}
    if float(comps.get("low_entropy") or 100) < 35:
        vetoes.append("High entropy / uncertainty")
    if float(comps.get("mean_confidence") or 100) < 35:
        vetoes.append("Low confidence")
    if float(comps.get("insurance_contribution") or 100) < 15 and float(comps.get("coverage_mass") or 0) < 55:
        vetoes.append("Weak insurance and weak coverage")
    if float(comps.get("league_reliability") or 100) < 35:
        vetoes.append("Weak historical league reliability")
    if diversification.get("over_concentrated"):
        vetoes.append("Too many correlated fixtures")
    n_elig = int(rankings.get("n_eligible") or 0)
    if n_elig == 0:
        vetoes.append("No fixtures cleared minimum investment priority")

    action = base
    if vetoes:
        # Downgrade
        if action == "BET":
            action = "SMALL BET" if score >= 72 and n_elig >= 1 else "WATCH"
        elif action == "SMALL BET":
            action = "WATCH"
        elif action == "WATCH" and len(vetoes) >= 2:
            action = "SKIP"
        if len(vetoes) >= 3 or n_elig == 0:
            action = "SKIP"
        reasons = reasons + [f"Veto: {v}" for v in vetoes]

    dynamic_count = 0
    if action == "BET":
        dynamic_count = min(5, max(1, n_elig))
        if score >= 90:
            dynamic_count = min(5, n_elig)
        elif score >= 84:
            dynamic_count = min(3, n_elig)
        else:
            dynamic_count = min(2, n_elig)
    elif action == "SMALL BET":
        dynamic_count = min(2, n_elig)
    elif action == "WATCH":
        dynamic_count = 0
    else:
        dynamic_count = 0

    selected = [
        r
        for r in (rankings.get("rankings") or [])
        if r.get("eligible_for_capital") and float(r.get("investment_priority") or 0) >= MIN_FIXTURE_SCORE_TO_BET
    ][:dynamic_count]

    return {
        "research_only": True,
        "action": action,
        "base_recommendation": base,
        "daily_portfolio_score": score,
        "grade": daily.get("grade"),
        "vetoes": vetoes,
        "reasoning": reasons,
        "recommended_fixture_count": dynamic_count,
        "selected_fixture_ids": [int(r["fixture_id"]) for r in selected],
        "selected_fixtures": selected,
        "skip_day": action in {"SKIP", "WATCH"},
    }
