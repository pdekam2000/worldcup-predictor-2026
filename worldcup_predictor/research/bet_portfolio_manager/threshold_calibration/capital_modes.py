"""Capital-allocation method comparison — research-only. Kelly disabled by default."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import summarize_days
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    replay_all_days,
)


def _stake_weights(mode: str, priorities: list[float], residuals: list[float]) -> list[float]:
    n = len(priorities) or 1
    if mode == "equal":
        return [1.0] * n
    if mode == "risk_weighted":
        return [max(0.01, p) / max(1.0, r) for p, r in zip(priorities, residuals)]
    if mode == "capped_score_weighted":
        # Cap relative weight at 2x mean priority
        mean_p = (sum(priorities) / n) if priorities else 1.0
        return [min(p, 2.0 * mean_p) for p in priorities]
    if mode == "hybrid_score_risk":
        return [max(0.01, p) * (1.0 / (1.0 + r / 50.0)) for p, r in zip(priorities, residuals)]
    if mode == "fractional_kelly_research":
        # Research-only proxy: priority * confidence-like residual inverse; disabled by default in policy
        return [max(0.01, p * 0.25 / max(1.0, r / 20.0)) for p, r in zip(priorities, residuals)]
    # score_weighted (current)
    return [max(0.01, p) for p in priorities]


def _realloc_day(day: dict[str, Any], mode: str) -> dict[str, Any]:
    """Re-weight unit stakes among already-selected fixtures (decision frozen)."""
    selected = list(day.get("selected_fixture_ids") or [])
    scale = float(day.get("capital_scale") or 0.0)
    if not selected or scale <= 0:
        return {
            **day,
            "exposure_units": 0.0,
            "realized_pnl_evaluation_only": 0.0,
            "realized_wins": 0,
            "realized_losses": 0,
            "capital_mode_used": mode,
        }
    by_id = {int(f["fixture_id"]): f for f in (day.get("fixtures") or [])}
    priorities = []
    residuals = []
    for fid in selected:
        fx = by_id.get(int(fid)) or {}
        priorities.append(float(fx.get("investment_priority") or fx.get("confidence") or 50.0) * 100)
        residuals.append(float(fx.get("residual_mass") or 0.2) * 100)
    weights = _stake_weights(mode, priorities, residuals)
    wsum = sum(weights) or 1.0
    stakes = [(w / wsum) * scale * len(selected) for w in weights]
    # Round to 0.01 for deterministic dispersion
    stakes = [round(s, 2) for s in stakes]
    pnl = 0.0
    wins = losses = 0
    for fid, stake in zip(selected, stakes):
        fx = by_id.get(int(fid)) or {}
        if stake <= 0:
            continue
        if fx.get("hit_insurance") is True:
            odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
            pnl += stake * (odd - 1.0)
            wins += 1
        elif fx.get("hit_insurance") is False:
            pnl -= stake
            losses += 1
    exposure = sum(stakes)
    stake_disp = round(max(stakes) - min(stakes), 6) if stakes else 0.0
    return {
        **day,
        "exposure_units": round(exposure, 6),
        "realized_pnl_evaluation_only": round(pnl, 6),
        "realized_wins": wins,
        "realized_losses": losses,
        "capital_mode_used": mode,
        "stake_dispersion": stake_disp,
        "concentration": round(max(stakes) / exposure, 6) if exposure > 0 else 0.0,
    }


def _longest_losing_streak(days: list[dict[str, Any]]) -> int:
    streak = best = 0
    for d in days:
        if float(d.get("realized_pnl_evaluation_only") or 0) < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def calibrate_capital_modes(
    fixtures: list[dict[str, Any]],
    *,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Compare allocation methods on the same locked selection decisions."""
    base_days = replay_all_days(fixtures, policy=policy)
    modes = (
        "equal",
        "score_weighted",
        "risk_weighted",
        "capped_score_weighted",
        "hybrid_score_risk",
        "fractional_kelly_research",
    )
    by_mode = {}
    for mode in modes:
        remapped = [_realloc_day(d, mode) for d in base_days]
        m = summarize_days(remapped)
        dispersions = [float(d.get("stake_dispersion") or 0) for d in remapped if float(d.get("exposure_units") or 0) > 0]
        concentrations = [float(d.get("concentration") or 0) for d in remapped if float(d.get("exposure_units") or 0) > 0]
        by_mode[mode] = {
            **m,
            "concentration": round(sum(concentrations) / len(concentrations), 6) if concentrations else 0.0,
            "capital_efficiency": m.get("roi"),
            "longest_losing_streak": _longest_losing_streak(remapped),
            "maximum_daily_loss": m.get("max_daily_loss"),
            "stake_dispersion": round(sum(dispersions) / len(dispersions), 6) if dispersions else 0.0,
            "kelly_default_disabled": mode == "fractional_kelly_research",
        }
    return {
        "research_only": True,
        "kelly_disabled_by_default": True,
        "selection_locked_from_policy": policy.get("policy_version"),
        "by_mode": by_mode,
        "recommended_default": "score_weighted",
    }
