"""Profit-aware scenario engine for five-bet Top10 evaluation."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer.constants import (
    CLASS_BREAK_EVEN,
    CLASS_FULL_LOSS,
    CLASS_PARTIAL,
    CLASS_PROFIT,
    CLASS_UNKNOWN,
    LOSS,
    PUSH,
    UNSUPPORTED,
    WIN,
)
from worldcup_predictor.research.top10_to_5_optimizer.market_semantics import settles_as_win
from worldcup_predictor.research.top10_to_5_optimizer.models import MarketCandidate


def _parse(score: str) -> tuple[int, int] | None:
    parts = str(score).replace(" ", "").split("-")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _settle_leg(leg: dict[str, Any], hg: int, ag: int) -> str:
    return settles_as_win(str(leg["market_type"]), dict(leg.get("market_parameters") or {}), hg, ag)


def classify_net(net: float | None, *, missing_odds: bool) -> str:
    if missing_odds or net is None:
        return CLASS_UNKNOWN
    if net > 1e-9:
        return CLASS_PROFIT
    if abs(net) <= 1e-9:
        return CLASS_BREAK_EVEN
    # Partial recovery: some return but still negative
    return CLASS_PARTIAL if net > -1e9 else CLASS_FULL_LOSS


def simulate_scoreline(
    scoreline: str,
    *,
    exact_legs: list[dict[str, Any]],
    market_legs: list[dict[str, Any]],
    stakes: dict[str, float],
) -> dict[str, Any]:
    parsed = _parse(scoreline)
    if parsed is None:
        return {
            "actual_scoreline": scoreline,
            "classification": CLASS_UNKNOWN,
            "net_profit_loss": None,
        }
    hg, ag = parsed
    legs = []
    for i, leg in enumerate(exact_legs, start=1):
        key = f"exact_{i}"
        legs.append({**leg, "leg_key": key, "stake": float(stakes.get(key) or 0.0)})
    for i, leg in enumerate(market_legs, start=1):
        key = f"market_{i}"
        legs.append({**leg, "leg_key": key, "stake": float(stakes.get(key) or 0.0)})

    winning, losing, pushing = [], [], []
    missing = False
    gross = 0.0
    total_stake = 0.0
    for leg in legs:
        stake = float(leg.get("stake") or 0.0)
        total_stake += stake
        outcome = _settle_leg(leg, hg, ag)
        odds = leg.get("decimal_odds")
        if outcome == WIN:
            winning.append(leg["leg_key"])
            if odds is None or float(odds) <= 1.0:
                missing = True
            else:
                gross += stake * float(odds)
        elif outcome == PUSH:
            pushing.append(leg["leg_key"])
            gross += stake  # stake returned
        elif outcome == LOSS:
            losing.append(leg["leg_key"])
        else:
            missing = True
            losing.append(leg["leg_key"])

    if missing:
        net = None
        classification = CLASS_UNKNOWN
        return_ratio = None
    else:
        net = round(gross - total_stake, 8)
        if net > 1e-9:
            classification = CLASS_PROFIT
        elif abs(net) <= 1e-9:
            classification = CLASS_BREAK_EVEN
        elif gross > 1e-12:
            classification = CLASS_PARTIAL
        else:
            classification = CLASS_FULL_LOSS
        return_ratio = round(gross / total_stake, 8) if total_stake > 0 else None

    return {
        "actual_scoreline": f"{hg}-{ag}",
        "winning_selections": winning,
        "losing_selections": losing,
        "push_selections": pushing,
        "total_stake": round(total_stake, 8),
        "gross_return": None if missing else round(gross, 8),
        "net_profit_loss": net,
        "return_ratio": return_ratio,
        "classification": classification,
        "profitably_covered": bool(net is not None and net >= 0),
        "raw_outcome_covered": bool(winning) or bool(pushing),
    }


def evaluate_top10_scenarios(
    top10: list[dict[str, Any]],
    *,
    exact_scores: list[str],
    market1: MarketCandidate | dict[str, Any],
    market2: MarketCandidate | dict[str, Any],
    stakes: dict[str, float],
    exact_odds: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    exact_odds = exact_odds or {}
    exact_legs = []
    for sc in exact_scores:
        exact_legs.append(
            {
                "market_type": "exact_score",
                "market_parameters": {"score": sc},
                "label": f"Exact {sc}",
                "decimal_odds": exact_odds.get(sc),
            }
        )

    def _as_leg(m: MarketCandidate | dict[str, Any]) -> dict[str, Any]:
        if isinstance(m, MarketCandidate):
            return {
                "market_type": m.market_type,
                "market_parameters": dict(m.market_parameters),
                "label": m.label,
                "decimal_odds": m.decimal_odds,
            }
        return {
            "market_type": m["market_type"],
            "market_parameters": dict(m.get("market_parameters") or {}),
            "label": m.get("label") or m.get("market_key"),
            "decimal_odds": m.get("decimal_odds"),
        }

    mlegs = [_as_leg(market1), _as_leg(market2)]
    rows = []
    for row in top10:
        sc = str(row.get("scoreline") or row.get("score") or "")
        p = float(row.get("probability") or 0.0)
        sim = simulate_scoreline(sc, exact_legs=exact_legs, market_legs=mlegs, stakes=stakes)
        sim["probability"] = p
        rows.append(sim)

    def _mass(pred) -> float:
        return round(sum(float(r["probability"]) for r in rows if pred(r)), 8)

    return {
        "rows": rows,
        "raw_outcome_coverage_mass": _mass(lambda r: r.get("raw_outcome_covered")),
        "profitable_outcome_coverage_mass": _mass(lambda r: r.get("profitably_covered")),
        "break_even_mass": _mass(lambda r: r.get("classification") == CLASS_BREAK_EVEN),
        "partial_recovery_mass": _mass(lambda r: r.get("classification") == CLASS_PARTIAL),
        "full_loss_mass": _mass(lambda r: r.get("classification") == CLASS_FULL_LOSS),
        "unknown_mass": _mass(lambda r: r.get("classification") == CLASS_UNKNOWN),
        "top10_probability_mass": round(sum(float(r.get("probability") or 0) for r in rows), 8),
        "expected_net": round(
            sum(float(r["probability"]) * float(r["net_profit_loss"]) for r in rows if r.get("net_profit_loss") is not None),
            8,
        )
        if all(r.get("net_profit_loss") is not None for r in rows)
        else None,
        "worst_top10_loss": min((float(r["net_profit_loss"]) for r in rows if r.get("net_profit_loss") is not None), default=None),
        "best_top10_profit": max((float(r["net_profit_loss"]) for r in rows if r.get("net_profit_loss") is not None), default=None),
    }
