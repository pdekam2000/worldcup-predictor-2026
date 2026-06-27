"""Bankroll stake sizing — Phase A17 (planning only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.betting_plan.constants import RISK_PROFILES


def _stake_pct_for_quality(
    quality: float,
    *,
    min_pct: float,
    max_pct: float,
) -> float:
    q = max(0.0, min(100.0, float(quality)))
    span = max_pct - min_pct
    return min_pct + (q / 100.0) * span


def recommend_stake(
    bankroll: float,
    *,
    profile: str = "balanced",
    bet_quality_score: float,
    is_combo: bool = False,
) -> dict[str, Any]:
    bankroll = max(0.0, float(bankroll))
    prof = RISK_PROFILES.get((profile or "balanced").lower(), RISK_PROFILES["balanced"])
    key = "combo" if is_combo else "single"
    lo, hi = prof[key]
    pct = _stake_pct_for_quality(bet_quality_score, min_pct=lo, max_pct=hi)
    stake = round(bankroll * pct, 2)
    return {
        "recommended_stake": stake,
        "stake_pct": round(pct * 100, 2),
        "stake_range_pct": [round(lo * 100, 2), round(hi * 100, 2)],
        "profile": profile,
        "bankroll": bankroll,
        "max_daily_exposure_pct": round(hi * 100 * (4 if is_combo else 6), 2),
    }


def attach_stakes(
    items: list[dict[str, Any]],
    *,
    bankroll: float,
    profile: str,
    is_combo: bool = False,
) -> list[dict[str, Any]]:
    out = []
    for item in items:
        q = float(item.get("bet_quality_score") or item.get("combined_quality") or 50)
        stake_info = recommend_stake(bankroll, profile=profile, bet_quality_score=q, is_combo=is_combo)
        merged = dict(item)
        merged["stake"] = stake_info
        if item.get("odds_decimal") and stake_info["recommended_stake"]:
            try:
                merged["potential_return"] = round(
                    stake_info["recommended_stake"] * float(item["odds_decimal"]), 2
                )
            except (TypeError, ValueError):
                merged["potential_return"] = None
        out.append(merged)
    return out


def portfolio_exposure(
    singles: list[dict[str, Any]],
    combos: list[dict[str, Any]],
    *,
    bankroll: float,
) -> dict[str, Any]:
    bankroll = max(0.0, float(bankroll))
    stakes = [float(s.get("stake", {}).get("recommended_stake") or 0) for s in singles]
    stakes += [float(c.get("stake", {}).get("recommended_stake") or 0) for c in combos]
    total_stake = round(sum(stakes), 2)
    exposure_pct = round((total_stake / bankroll) * 100, 2) if bankroll > 0 else 0.0
    qualities = [float(s.get("bet_quality_score") or 0) for s in singles]
    avg_q = round(sum(qualities) / len(qualities), 1) if qualities else None
    returns = [s.get("potential_return") for s in singles + combos if s.get("potential_return")]
    expected_return = round(sum(returns), 2) if returns else None
    return {
        "bet_count": len(singles) + len(combos),
        "total_stake": total_stake,
        "total_exposure_pct": exposure_pct,
        "average_quality": avg_q,
        "expected_return": expected_return,
        "risk_warning": "High exposure" if exposure_pct > 15 else ("Moderate exposure" if exposure_pct > 8 else "Low exposure"),
    }
