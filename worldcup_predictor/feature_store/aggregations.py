"""Rolling xG aggregation helpers for feature store."""

from __future__ import annotations

from statistics import mean
from typing import Any


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def compute_team_rolling_xg(
    team_history: list[dict[str, Any]],
    *,
    window: int = 5,
) -> dict[str, Any]:
    """
    Compute rolling xG features from ordered team match history (newest last).

    Each history row expects: xg_for, xg_against, is_home (optional).
    """
    if not team_history or window <= 0:
        return {
            "window": window,
            "matches_used": 0,
            "rolling_xg_for": None,
            "rolling_xga": None,
            "home_xg": None,
            "away_xg": None,
            "xg_trend": None,
            "xg_momentum": None,
            "attack_strength": None,
            "defensive_weakness": None,
            "features_json": {},
        }

    slice_rows = team_history[-window:]
    xg_for = [float(r["xg_for"]) for r in slice_rows if r.get("xg_for") is not None]
    xga = [float(r["xg_against"]) for r in slice_rows if r.get("xg_against") is not None]
    home_xg_vals = [
        float(r["xg_for"]) for r in slice_rows if r.get("is_home") and r.get("xg_for") is not None
    ]
    away_xg_vals = [
        float(r["xg_for"])
        for r in slice_rows
        if r.get("is_home") is False and r.get("xg_for") is not None
    ]

    rolling_for = _avg(xg_for)
    rolling_xga = _avg(xga)
    trend = None
    if len(xg_for) >= 3:
        first_half = _avg(xg_for[: len(xg_for) // 2])
        second_half = _avg(xg_for[len(xg_for) // 2 :])
        if first_half is not None and second_half is not None:
            trend = round(second_half - first_half, 4)

    momentum = None
    if rolling_for is not None and rolling_xga is not None:
        momentum = round(rolling_for - rolling_xga, 4)

    attack_strength = rolling_for
    defensive_weakness = rolling_xga

    features = {
        "rolling_xg_for": rolling_for,
        "rolling_xga": rolling_xga,
        "home_xg_avg": _avg(home_xg_vals),
        "away_xg_avg": _avg(away_xg_vals),
        "xg_trend": trend,
        "xg_momentum": momentum,
        "attack_strength": attack_strength,
        "defensive_weakness": defensive_weakness,
        "matches_used": len(slice_rows),
    }
    return {"window": window, "features_json": features, **features}


def build_fixture_rolling_context(
    home_history: list[dict[str, Any]],
    away_history: list[dict[str, Any]],
    *,
    window: int = 5,
) -> dict[str, Any]:
    """Merge home/away rolling features for fixture enrichment."""
    home = compute_team_rolling_xg(home_history, window=window)
    away = compute_team_rolling_xg(away_history, window=window)
    return {
        "window": window,
        "home_team_recent_xg": home.get("rolling_xg_for"),
        "away_team_recent_xg": away.get("rolling_xg_for"),
        "home_team_recent_xga": home.get("rolling_xga"),
        "away_team_recent_xga": away.get("rolling_xga"),
        "features_json": {
            "home": home.get("features_json") or {},
            "away": away.get("features_json") or {},
        },
    }
