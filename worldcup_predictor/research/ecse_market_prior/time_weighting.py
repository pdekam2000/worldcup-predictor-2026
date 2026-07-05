"""Time-based neighbor weighting schemes."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal, Sequence

TimeScheme = Literal[
    "equal",
    "decay_180d",
    "decay_365d",
    "decay_730d",
    "last_2_seasons",
    "last_4_seasons",
]


def _parse_date(text: str) -> datetime:
    return datetime.strptime(text[:10], "%Y-%m-%d")


def days_between(older: str, newer: str) -> float:
    return max(0.0, (_parse_date(newer) - _parse_date(older)).days)


def exponential_decay_weight(days_apart: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return math.pow(0.5, days_apart / half_life_days)


def season_year(date_text: str) -> int:
    dt = _parse_date(date_text)
    return dt.year if dt.month >= 7 else dt.year - 1


def apply_time_weights(
    neighbor_dates: Sequence[str],
    target_date: str,
    scheme: TimeScheme,
) -> list[float]:
    if scheme == "equal":
        return [1.0] * len(neighbor_dates)

    if scheme.startswith("decay_"):
        half = {"decay_180d": 180.0, "decay_365d": 365.0, "decay_730d": 730.0}[scheme]
        return [exponential_decay_weight(days_between(d, target_date), half) for d in neighbor_dates]

    target_season = season_year(target_date)
    if scheme == "last_2_seasons":
        min_season = target_season - 1
    elif scheme == "last_4_seasons":
        min_season = target_season - 3
    else:
        min_season = 0

    weights: list[float] = []
    for d in neighbor_dates:
        weights.append(1.0 if season_year(d) >= min_season else 0.0)
    return weights
