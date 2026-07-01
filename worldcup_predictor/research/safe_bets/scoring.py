"""PHASE SAFE-BETS-1 — Probability buckets, traps, usefulness scoring."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.safe_bets.markets import (
    is_trivial_trap_market,
    market_usefulness_bonus,
)

PHASE = "SAFE-BETS-1"

TRAP_ODDS_MAX = 1.05
HIGH_MARGIN_OVERROUND = 1.12
MIN_STORE_IMPLIED = 0.75


def implied_probability(odds: float) -> float:
    if odds < 1.0:
        return 0.0
    return 1.0 / odds


def probability_bucket(prob: float) -> str | None:
    if prob >= 0.90:
        return "90%+"
    if prob >= 0.85:
        return "85-90%"
    if prob >= 0.75:
        return "75-85%"
    return None


def devig_two_way(odd_a: float, odd_b: float) -> tuple[float, float]:
    ia, ib = implied_probability(odd_a), implied_probability(odd_b)
    total = ia + ib
    if total <= 0:
        return ia, ib
    return ia / total, ib / total


def estimate_devigged(
    implied: float,
    *,
    market_type: str,
    all_implied_in_market: list[float] | None = None,
) -> float:
    if all_implied_in_market and len(all_implied_in_market) >= 2:
        total = sum(all_implied_in_market)
        if total > 0:
            return implied / total
    if market_type in {"double_chance", "btts", "goals_ou", "corners_ou", "cards_ou"}:
        return min(implied * 1.02, 0.99)
    return implied


def detect_traps(
    *,
    odds: float,
    implied: float,
    devigged: float,
    market_type: str,
    market_name: str,
    selection: str,
    allow_trivial: bool = False,
    overround: float | None = None,
) -> tuple[bool, str]:
    reasons: list[str] = []
    if odds <= TRAP_ODDS_MAX:
        reasons.append("low_odds_trap")
    trivial, t_reason = is_trivial_trap_market(market_type, market_name, selection)
    if trivial and not allow_trivial:
        reasons.append(t_reason)
    if overround is not None and overround > HIGH_MARGIN_OVERROUND:
        reasons.append("high_bookmaker_margin")
    if market_type == "asian_handicap" and abs(implied - devigged) > 0.15:
        reasons.append("ah_margin_uncertain")
    if reasons:
        return True, ";".join(reasons)
    return False, ""


def usefulness_score(
    *,
    devigged: float,
    market_type: str,
    odds: float,
    trap_flag: bool,
    trap_reason: str,
    data_quality: float,
) -> float:
    base = devigged * 100.0
    base += market_usefulness_bonus(market_type)
    base += data_quality * 5.0
    if odds <= TRAP_ODDS_MAX:
        base -= 35.0
    if trap_flag:
        base -= 25.0
        if "trivial" in trap_reason:
            base -= 20.0
    return round(max(0.0, min(100.0, base)), 2)


def score_candidate(
    *,
    odds: float,
    market_type: str,
    market_name: str,
    selection: str,
    data_quality: float = 0.7,
    allow_trivial: bool = False,
    peer_implied: list[float] | None = None,
    overround: float | None = None,
) -> dict[str, Any] | None:
    implied = implied_probability(odds)
    bucket = probability_bucket(implied)
    if bucket is None and implied < MIN_STORE_IMPLIED:
        return None
    devigged = estimate_devigged(implied, market_type=market_type, all_implied_in_market=peer_implied)
    trap, reason = detect_traps(
        odds=odds,
        implied=implied,
        devigged=devigged,
        market_type=market_type,
        market_name=market_name,
        selection=selection,
        allow_trivial=allow_trivial,
        overround=overround,
    )
    if bucket is None and not trap:
        return None
    useful = usefulness_score(
        devigged=devigged,
        market_type=market_type,
        odds=odds,
        trap_flag=trap,
        trap_reason=reason,
        data_quality=data_quality,
    )
    return {
        "implied_probability": round(implied, 6),
        "devigged_probability": round(devigged, 6),
        "probability_bucket": bucket or ("90%+" if implied >= 0.9 else "75-85%"),
        "usefulness_score": useful,
        "trap_flag": trap,
        "reason": reason or None,
    }
