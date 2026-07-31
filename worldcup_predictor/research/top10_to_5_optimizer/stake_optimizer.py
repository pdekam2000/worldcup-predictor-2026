"""Stake allocation modes for five-leg Top10-to-5 plans."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer.constants import STAKE_MODES


def _round_step(x: float, step: float) -> float:
    if step <= 0:
        return round(x, 2)
    return round(round(x / step) * step, 8)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _renormalize(
    raw: dict[str, float],
    *,
    budget: float,
    minimum: float,
    maximum: float,
    step: float,
    required_keys: list[str],
) -> dict[str, float]:
    # Ensure required keys present and > 0
    out = {k: float(raw.get(k) or 0.0) for k in required_keys}
    for k in required_keys:
        if out[k] < minimum:
            out[k] = minimum
        out[k] = _clip(out[k], minimum, maximum)
        out[k] = _round_step(out[k], step)
        if out[k] < minimum:
            out[k] = minimum

    total = sum(out.values())
    if total <= 0:
        eq = _round_step(budget / len(required_keys), step)
        return {k: _clip(eq, minimum, maximum) for k in required_keys}

    # Scale toward budget
    scale = budget / total
    scaled = {k: _clip(_round_step(v * scale, step), minimum, maximum) for k, v in out.items()}
    # Fix residual by adjusting largest stake
    diff = round(budget - sum(scaled.values()), 8)
    if abs(diff) >= step / 2:
        kmax = max(scaled, key=scaled.get)
        scaled[kmax] = _clip(_round_step(scaled[kmax] + diff, step), minimum, maximum)
    # Final guarantee no zero
    for k in required_keys:
        if scaled[k] < minimum:
            scaled[k] = minimum
    # If over budget after floors, shrink non-exact markets first
    while sum(scaled.values()) > budget + 1e-9:
        adjustable = [k for k in ("market_2", "market_1", "exact_3", "exact_2", "exact_1") if scaled[k] > minimum]
        if not adjustable:
            break
        k = adjustable[0]
        scaled[k] = _round_step(scaled[k] - step, step)
        if scaled[k] < minimum:
            scaled[k] = minimum
    return {k: round(float(scaled[k]), 8) for k in required_keys}


def allocate_stakes(
    *,
    mode: str,
    budget: float,
    minimum: float = 1.0,
    maximum: float = 10.0,
    step: float = 0.5,
    exact_probs: list[float] | None = None,
    top10_probs: list[float] | None = None,
    kelly_fraction: float = 0.25,
    kelly_enabled: bool = False,
) -> dict[str, Any]:
    keys = ["exact_1", "exact_2", "exact_3", "market_1", "market_2"]
    mode = str(mode or "equal_stake")
    if mode not in STAKE_MODES:
        mode = "equal_stake"
    if mode == "fractional_kelly_research" and not kelly_enabled:
        mode = "equal_stake"

    exact_probs = list(exact_probs or [0.2, 0.15, 0.1])
    while len(exact_probs) < 3:
        exact_probs.append(0.05)

    if mode == "equal_stake":
        raw = {k: budget / 5.0 for k in keys}
    elif mode == "probability_weighted":
        weights = [max(1e-6, float(p)) for p in exact_probs[:3]] + [sum(exact_probs[:3]) * 0.5, sum(exact_probs[:3]) * 0.5]
        s = sum(weights) or 1.0
        raw = {k: budget * (w / s) for k, w in zip(keys, weights)}
    elif mode == "score_weighted":
        weights = [max(1e-6, float(p)) for p in exact_probs[:3]] + [0.25, 0.25]
        s = sum(weights) or 1.0
        raw = {k: budget * (w / s) for k, w in zip(keys, weights)}
    elif mode == "profit_floor":
        # Heavier exact stakes + balanced coverage
        raw = {
            "exact_1": budget * 0.22,
            "exact_2": budget * 0.20,
            "exact_3": budget * 0.18,
            "market_1": budget * 0.22,
            "market_2": budget * 0.18,
        }
    elif mode == "minmax_loss":
        # Prefer more on coverage markets to reduce worst-case bare miss
        raw = {
            "exact_1": budget * 0.16,
            "exact_2": budget * 0.16,
            "exact_3": budget * 0.16,
            "market_1": budget * 0.26,
            "market_2": budget * 0.26,
        }
    elif mode == "fractional_kelly_research":
        # Research-only heuristic: scale exact by p*(odds_proxy-1); odds unknown → fall back
        weights = [max(1e-6, float(p)) * kelly_fraction for p in exact_probs[:3]] + [0.2, 0.2]
        s = sum(weights) or 1.0
        raw = {k: budget * (w / s) for k, w in zip(keys, weights)}
    else:
        raw = {k: budget / 5.0 for k in keys}

    stakes = _renormalize(raw, budget=budget, minimum=minimum, maximum=maximum, step=step, required_keys=keys)
    return {
        "stake_mode": mode,
        "stakes": stakes,
        "total_budget": round(sum(stakes.values()), 8),
        "requested_budget": float(budget),
        "minimum_stake_eur": minimum,
        "maximum_stake_eur": maximum,
        "rounding_step_eur": step,
        "fractional_kelly_enabled": bool(kelly_enabled and mode == "fractional_kelly_research"),
        "research_only": True,
    }
