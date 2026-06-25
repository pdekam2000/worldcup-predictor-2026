"""Pressure timeline aggregation helpers."""

from __future__ import annotations

from statistics import mean
from typing import Any

from worldcup_predictor.feature_store.pressure_store.models import SportmonksPressureRecord

AGGREGATION_KEYS = (
    "average_pressure",
    "max_pressure",
    "pressure_first_15",
    "pressure_first_30",
    "pressure_before_first_goal",
    "pressure_spike_count",
    "pressure_dominance",
    "pressure_momentum",
    "pressure_swing",
    "pressure_last_5",
    "pressure_last_10",
)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _team_rows(
    records: list[SportmonksPressureRecord],
    participant_id: int,
) -> list[SportmonksPressureRecord]:
    return [r for r in records if r.participant_id == participant_id]


def _minute_map(rows: list[SportmonksPressureRecord]) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rows:
        out[r.minute] = float(r.pressure_value)
    return out


def compute_team_pressure_features(
    rows: list[SportmonksPressureRecord],
    *,
    first_goal_minute: int | None = None,
    spike_percentile: float = 0.9,
) -> dict[str, Any]:
    if not rows:
        return {k: None for k in AGGREGATION_KEYS}

    values = [float(r.pressure_value) for r in rows]
    by_minute = _minute_map(rows)
    sorted_minutes = sorted(by_minute.keys())

    first_15 = [by_minute[m] for m in sorted_minutes if m <= 15]
    first_30 = [by_minute[m] for m in sorted_minutes if m <= 30]
    before_goal = (
        [by_minute[m] for m in sorted_minutes if first_goal_minute is not None and m < first_goal_minute]
        if first_goal_minute is not None
        else None
    )

    last_5_minutes = sorted_minutes[-5:] if len(sorted_minutes) >= 5 else sorted_minutes
    last_10_minutes = sorted_minutes[-10:] if len(sorted_minutes) >= 10 else sorted_minutes
    last_5 = [by_minute[m] for m in last_5_minutes]
    last_10 = [by_minute[m] for m in last_10_minutes]

    threshold = sorted(values)[max(0, int(len(values) * spike_percentile) - 1)] if values else 0.0
    spikes = sum(1 for v in values if v >= threshold and v > 0)

    momentum = None
    if len(sorted_minutes) >= 10:
        early = _avg([by_minute[m] for m in sorted_minutes[:5]])
        late = _avg([by_minute[m] for m in sorted_minutes[-5:]])
        if early is not None and late is not None:
            momentum = round(late - early, 4)

    swing = 0.0
    for i in range(1, len(sorted_minutes)):
        m0, m1 = sorted_minutes[i - 1], sorted_minutes[i]
        swing = max(swing, abs(by_minute[m1] - by_minute[m0]))

    return {
        "average_pressure": _avg(values),
        "max_pressure": round(max(values), 4) if values else None,
        "pressure_first_15": _avg(first_15),
        "pressure_first_30": _avg(first_30),
        "pressure_before_first_goal": _avg(before_goal) if before_goal is not None else None,
        "pressure_spike_count": spikes,
        "pressure_dominance": None,
        "pressure_momentum": momentum,
        "pressure_swing": round(swing, 4),
        "pressure_last_5": _avg(last_5),
        "pressure_last_10": _avg(last_10),
    }


def compute_fixture_pressure_features(
    records: list[SportmonksPressureRecord],
    *,
    home_participant_id: int,
    away_participant_id: int,
    first_goal_minute: int | None = None,
) -> dict[str, Any]:
    home_rows = _team_rows(records, home_participant_id)
    away_rows = _team_rows(records, away_participant_id)

    home = compute_team_pressure_features(home_rows, first_goal_minute=first_goal_minute)
    away = compute_team_pressure_features(away_rows, first_goal_minute=first_goal_minute)

    total_pressure = sum(float(r.pressure_value) for r in records)
    home_sum = sum(float(r.pressure_value) for r in home_rows)
    away_sum = sum(float(r.pressure_value) for r in away_rows)
    if total_pressure > 0:
        home["pressure_dominance"] = round(home_sum / total_pressure, 4)
        away["pressure_dominance"] = round(away_sum / total_pressure, 4)

    match_level: dict[str, Any] = {}
    if home.get("average_pressure") is not None and away.get("average_pressure") is not None:
        match_level["pressure_asymmetry"] = round(
            float(home["average_pressure"]) - float(away["average_pressure"]), 4
        )
    if home.get("pressure_first_15") is not None and away.get("pressure_first_15") is not None:
        match_level["pressure_first_15_edge"] = round(
            float(home["pressure_first_15"]) - float(away["pressure_first_15"]), 4
        )

    return {
        "home": home,
        "away": away,
        "match": match_level,
        "first_goal_minute": first_goal_minute,
    }
