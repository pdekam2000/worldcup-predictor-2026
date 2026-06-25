"""Phase 54P goalscorer intelligence models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ConfidenceTier = Literal["A", "B", "C", "D"]

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_ELITE_CANDIDATE",
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_MEDIUM_VALUE",
    }
)

COMPOSITE_WEIGHTS: dict[str, float] = {
    "ml_score": 0.35,
    "odds_implied": 0.25,
    "starter_probability": 0.15,
    "recent_form": 0.10,
    "xg_per_90": 0.08,
    "shots_on_target": 0.07,
}


@dataclass
class PlayerIntelligence:
    sportmonks_fixture_id: int
    player_id: int
    player_name: str
    team_id: int | None
    ml_score: float
    odds_implied_anytime: float | None
    odds_implied_first: float | None
    starter_probability: float
    recent_form_score: float
    xg_per_90: float
    shots_on_target_last_5: int
    lineup_status: str
    composite_scorer_score: float
    composite_first_goal_score: float
    ml_rank: int
    odds_rank: int
    value_gap: float
    confidence_tier: ConfidenceTier
    is_surprise_candidate: bool
    is_value_pick: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FixtureIntelligence:
    sportmonks_fixture_id: int
    api_football_fixture_id: int | None
    home_team: str | None
    away_team: str | None
    match_date: str | None
    top_anytime_scorers: list[dict[str, Any]]
    top_first_goalscorers: list[dict[str, Any]]
    top_surprise_candidates: list[dict[str, Any]]
    top_value_candidates: list[dict[str, Any]]
    top_team_scoring_threats: list[dict[str, Any]]
    confidence_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplayMetrics:
    market: str
    signal: str
    fixtures_evaluated: int
    top1_hit: float
    top3_hit: float
    top5_hit: float
    mrr: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
