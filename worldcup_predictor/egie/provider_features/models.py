"""EGIE paid provider feature vectors (Phase API utilization)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProviderFeatureVector:
    fixture_id: int
    competition_key: str
    home_xg_for: float | None = None
    away_xg_for: float | None = None
    home_xg_against: float | None = None
    away_xg_against: float | None = None
    pressure_index_home: float | None = None
    pressure_index_away: float | None = None
    home_shots: float | None = None
    away_shots: float | None = None
    home_shots_on_target: float | None = None
    away_shots_on_target: float | None = None
    home_dangerous_attacks: float | None = None
    away_dangerous_attacks: float | None = None
    odds_implied_home: float | None = None
    odds_implied_away: float | None = None
    odds_implied_draw: float | None = None
    odds_movement_home: float | None = None
    lineup_strength_home: float | None = None
    lineup_strength_away: float | None = None
    injuries_impact_home: float | None = None
    injuries_impact_away: float | None = None
    recent_first_goal_home_rate: float | None = None
    recent_first_goal_away_rate: float | None = None
    coverage: dict[str, bool] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
