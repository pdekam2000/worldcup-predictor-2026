"""Capital allocation across selected fixtures (research-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.constants import (
    DEFAULT_BANKROLLS,
    KELLY_FRACTION,
    MAX_DAY_EXPOSURE_FRAC,
    MAX_FIXTURE_EXPOSURE_FRAC,
)


def _round_money(x: float, step: float = 0.5) -> float:
    if step <= 0:
        return round(x, 2)
    return round(round(x / step) * step, 2)


def allocate_capital(
    *,
    bankroll: float,
    selected: list[dict[str, Any]],
    fixtures_by_id: dict[int, dict[str, Any]],
    mode: str = "score_weighted",
    max_day_frac: float = MAX_DAY_EXPOSURE_FRAC,
    max_fx_frac: float = MAX_FIXTURE_EXPOSURE_FRAC,
) -> dict[str, Any]:
    """
    Modes: equal | score_weighted | risk_weighted | fractional_kelly
    fractional_kelly is research-labeled only — not guaranteed profit.
    """
    mode_l = str(mode).lower().strip()
    bankroll = float(bankroll)
    day_budget = bankroll * float(max_day_frac)
    if not selected or day_budget <= 0:
        return {
            "research_only": True,
            "bankroll_eur": bankroll,
            "mode": mode_l,
            "day_budget_eur": round(day_budget, 2),
            "allocated_eur": 0.0,
            "allocations": [],
            "rejected": [{"fixture_id": r["fixture_id"], "reason": "NO_SELECTION"} for r in selected],
            "warning": "Research-only. Not guaranteed profit. Not deployed.",
        }

    weights: list[float] = []
    for r in selected:
        fid = int(r["fixture_id"])
        fx = fixtures_by_id.get(fid) or {}
        pri = max(0.0, float(r.get("investment_priority") or 0.0))
        residual = max(0.0, float(r.get("residual_risk") or 0.0))
        conf = max(0.0, float(r.get("confidence") or 0.0)) / 100.0
        odds = fx.get("insurance_odds") or fx.get("odds_home") or 2.0
        try:
            odds_f = float(odds)
        except (TypeError, ValueError):
            odds_f = 2.0
        if mode_l == "equal":
            weights.append(1.0)
        elif mode_l == "risk_weighted":
            weights.append(pri / max(1.0, residual))
        elif mode_l in {"fractional_kelly", "kelly_research"}:
            # Research fractional Kelly using confidence as p proxy
            b = max(0.01, odds_f - 1.0)
            edge = conf * odds_f - 1.0
            k = max(0.0, edge / b) * KELLY_FRACTION
            weights.append(k if k > 0 else pri / 100.0)
        else:  # score_weighted default
            weights.append(pri)

    wsum = sum(weights) or float(len(weights))
    allocations = []
    allocated = 0.0
    for r, w in zip(selected, weights):
        raw = day_budget * (w / wsum)
        cap = bankroll * float(max_fx_frac)
        stake = _round_money(min(raw, cap))
        stake = max(0.0, stake)
        allocations.append(
            {
                "fixture_id": int(r["fixture_id"]),
                "match_name": r.get("match_name"),
                "league": r.get("league"),
                "portfolio_rank": r.get("portfolio_rank"),
                "stake_eur": stake,
                "weight": round(w / wsum, 6),
                "investment_priority": r.get("investment_priority"),
            }
        )
        allocated += stake

    rejected = []
    return {
        "research_only": True,
        "bankroll_eur": bankroll,
        "mode": mode_l,
        "kelly_fraction": KELLY_FRACTION if "kelly" in mode_l else None,
        "day_budget_eur": round(day_budget, 2),
        "max_fixture_exposure_eur": round(bankroll * max_fx_frac, 2),
        "allocated_eur": round(allocated, 2),
        "unallocated_eur": round(max(0.0, day_budget - allocated), 2),
        "allocations": allocations,
        "rejected": rejected,
        "warning": "Research-only capital allocation. Not guaranteed profit. Not deployed.",
    }


def allocate_for_bankrolls(
    *,
    selected: list[dict[str, Any]],
    fixtures_by_id: dict[int, dict[str, Any]],
    bankrolls: tuple[float, ...] = DEFAULT_BANKROLLS,
    mode: str = "score_weighted",
) -> dict[str, Any]:
    return {
        "research_only": True,
        "mode": mode,
        "by_bankroll": {
            str(int(b)): allocate_capital(
                bankroll=float(b),
                selected=selected,
                fixtures_by_id=fixtures_by_id,
                mode=mode,
            )
            for b in bankrolls
        },
    }
