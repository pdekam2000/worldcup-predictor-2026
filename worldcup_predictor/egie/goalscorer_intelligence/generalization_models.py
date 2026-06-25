"""Phase 54Q generalization models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_ELITE_CONFIRMED",
        "GOALSCORER_HIGH_VALUE",
        "GOALSCORER_MEDIUM_VALUE",
    }
)

LEAGUE_LABELS: dict[int, str] = {
    732: "world_cup",
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}


@dataclass
class LeagueMetrics:
    league: str
    league_id: int
    fixtures: int
    fixtures_evaluated: int
    top1_hit: float
    top3_hit: float
    top5_hit: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RobustnessResult:
    scenario: str
    top3_hit: float
    top3_drop: float
    fixtures_evaluated: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TierReliability:
    tier: str
    sample_count: int
    fixture_count: int
    hit_rate: float
    brier: float | None
    ece: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
