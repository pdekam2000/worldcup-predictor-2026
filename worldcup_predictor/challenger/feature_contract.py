"""Prematch-only feature contract for Challenger models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FeatureContract:
    """Declares required/optional features and forbids post-match fields."""

    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = (
        "final_score",
        "home_goals_ft",
        "away_goals_ft",
        "post_match_stats",
        "result_1x2",
        "actual_btts",
        "actual_ou25",
        "closing_odds_after_prediction",
        "future_standings",
        "future_form",
    )

    def validate_keys(self, feature_keys: set[str]) -> tuple[list[str], list[str]]:
        missing = [k for k in self.required if k not in feature_keys]
        leaked = [k for k in self.forbidden if k in feature_keys]
        return missing, leaked


DEFAULT_GBGM_CONTRACT = FeatureContract(
    required=(
        "home_goals_for_avg_l5",
        "home_goals_against_avg_l5",
        "away_goals_for_avg_l5",
        "away_goals_against_avg_l5",
        "league_avg_home_goals",
        "league_avg_away_goals",
    ),
    optional=(
        "rest_days_home",
        "rest_days_away",
        "is_home",
        "implied_home",
        "implied_draw",
        "implied_away",
        "implied_over_25",
        "implied_under_25",
        "bookmaker_count",
        "elo_home",
        "elo_away",
        "missing_lineup",
        "missing_injuries",
    ),
)


def missingness_indicators(features: dict[str, Any], keys: tuple[str, ...]) -> dict[str, int]:
    return {f"missing__{k}": (0 if features.get(k) is not None else 1) for k in keys}
