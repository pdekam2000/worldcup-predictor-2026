"""Kaplan–Meier survival estimator for time-to-first-goal."""

from __future__ import annotations

from typing import Any


def fit_kaplan_meier(
    observations: list[tuple[float, int]],
    *,
    max_time: float = 90.0,
) -> dict[str, Any]:
    """
    Fit KM survival curve from (time, event) pairs.

    event=1 → first goal observed at `time`
    event=0 → censored at `time` (no goal by end of match)
    """
    if not observations:
        return _empty_curve(max_time)

    # Sort by time ascending
    data = sorted(((float(t), int(e)) for t, e in observations), key=lambda x: x[0])
    times = sorted({t for t, _ in data})

    n_at_risk = len(data)
    survival = 1.0
    curve: list[dict[str, float]] = [{"minute": 0.0, "survival": 1.0, "cdf": 0.0}]

    for t in times:
        deaths = sum(1 for ti, ei in data if ti == t and ei == 1)
        censored = sum(1 for ti, ei in data if ti == t and ei == 0)
        if n_at_risk <= 0:
            break
        if deaths > 0:
            survival *= 1.0 - (deaths / n_at_risk)
        curve.append(
            {
                "minute": float(t),
                "survival": round(max(0.0, survival), 6),
                "cdf": round(1.0 - max(0.0, survival), 6),
            }
        )
        n_at_risk -= deaths + censored

    # Extend flat tail to max_time
    if curve[-1]["minute"] < max_time:
        curve.append(
            {
                "minute": float(max_time),
                "survival": round(max(0.0, survival), 6),
                "cdf": round(1.0 - max(0.0, survival), 6),
            }
        )

    checkpoints = _checkpoint_probs(curve, (15, 30, 45, 60, 75, 90))
    return {
        "n": len(observations),
        "survival_curve": curve,
        "checkpoint_goal_probability": checkpoints,
    }


def survival_at(curve: list[dict[str, float]], minute: float) -> float:
    """P(no first goal by `minute`) — step function from KM curve."""
    if not curve:
        return 1.0
    s = 1.0
    for point in curve:
        if point["minute"] <= minute:
            s = float(point["survival"])
        else:
            break
    return max(0.0, min(1.0, s))


def goal_probability_before(curve: list[dict[str, float]], minute: float) -> float:
    """P(first goal occurs by minute X)."""
    return 1.0 - survival_at(curve, minute)


def _checkpoint_probs(curve: list[dict[str, float]], minutes: tuple[int, ...]) -> dict[str, float]:
    return {str(m): round(goal_probability_before(curve, float(m)), 4) for m in minutes}


def _empty_curve(max_time: float) -> dict[str, Any]:
    curve = [{"minute": 0.0, "survival": 1.0, "cdf": 0.0}, {"minute": max_time, "survival": 1.0, "cdf": 0.0}]
    return {
        "n": 0,
        "survival_curve": curve,
        "checkpoint_goal_probability": {str(m): 0.0 for m in (15, 30, 45, 60, 75, 90)},
    }
