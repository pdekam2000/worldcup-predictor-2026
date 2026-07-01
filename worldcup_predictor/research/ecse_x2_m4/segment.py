"""PHASE ECSE-X2-M4 — Target segment gate for internal weight application."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_x2_m4.constants import (
    HOME_FAVORITE_MARGIN,
    MIN_HOME_PROB,
    STRONG_HOME_FAVORITE_MARGIN,
    STRONG_HOME_PROB,
)


def _is_finite_prob(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def classify_match_state(probs: dict[str, float | None]) -> str:
    h = probs.get("ft_home")
    a = probs.get("ft_away")
    if h is not None and a is not None:
        if h - a >= HOME_FAVORITE_MARGIN:
            return "home_favorite"
        if a - h >= HOME_FAVORITE_MARGIN:
            return "away_favorite"
        return "balanced"
    if h is None:
        return "unknown"
    if h >= 0.45:
        return "home_favorite"
    if h <= 0.32:
        return "away_favorite"
    return "balanced"


def is_strong_home_favorite(probs: dict[str, float | None]) -> bool:
    h = probs.get("ft_home")
    a = probs.get("ft_away")
    if h is None or h < STRONG_HOME_PROB:
        return False
    if a is not None:
        return h - a >= STRONG_HOME_FAVORITE_MARGIN
    return h >= STRONG_HOME_PROB


def odds_snapshot_valid(probs: dict[str, float | None], coverage: int | None) -> bool:
    if not _is_finite_prob(probs.get("ft_home")):
        return False
    if int(coverage or 0) < 1:
        return False
    return True


def evaluate_target_segment(
    probs: dict[str, float | None],
    *,
    coverage: int | None = None,
) -> dict[str, Any]:
    home = probs.get("ft_home")
    state = classify_match_state(probs)

    if home is None:
        return _reject("missing_ft_home")
    if not _is_finite_prob(home):
        return _reject("invalid_home_prob")
    if not odds_snapshot_valid(probs, coverage):
        return _reject("invalid_odds_snapshot")
    if state == "balanced":
        return _reject("balanced_match")
    if state != "home_favorite":
        return _reject("not_home_favorite")
    if home < MIN_HOME_PROB:
        return _reject("home_prob_below_55")

    return {
        "target_segment_passed": True,
        "exclusion_reason": None,
        "home_prob": round(float(home), 6),
        "match_state": state,
        "strong_home_favorite": is_strong_home_favorite(probs),
    }


def _reject(reason: str) -> dict[str, Any]:
    return {
        "target_segment_passed": False,
        "exclusion_reason": reason,
        "home_prob": None,
        "match_state": None,
        "strong_home_favorite": False,
    }
