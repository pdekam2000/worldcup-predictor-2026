"""Outcome persistence models — Phase 46C-1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MatchOutcomeType = Literal[
    "FT",
    "AET",
    "PEN",
    "CANCELLED",
    "ABANDONED",
    "AWARDED",
    "POSTPONED",
    "UNKNOWN",
]

HtResult = Literal["home_win", "draw", "away_win"]


@dataclass(frozen=True)
class GoalEvent:
    sort_index: int
    minute: int | None
    extra_minute: int | None
    team: str | None
    team_id: int | None
    player: str | None
    assist: str | None
    is_penalty: bool
    is_own_goal: bool
    detail: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> GoalEvent:
        return cls(
            sort_index=int(row["sort_index"]),
            minute=int(row["minute"]) if row.get("minute") is not None else None,
            extra_minute=int(row["extra_minute"]) if row.get("extra_minute") is not None else None,
            team=row.get("team"),
            team_id=int(row["team_id"]) if row.get("team_id") is not None else None,
            player=row.get("player"),
            assist=row.get("assist"),
            is_penalty=bool(row.get("is_penalty")),
            is_own_goal=bool(row.get("is_own_goal")),
            detail=row.get("detail"),
        )


@dataclass
class ParsedFixtureOutcome:
    fixture_id: int
    match_outcome_type: str
    ht_home_goals: int | None = None
    ht_away_goals: int | None = None
    ht_result: str | None = None
    ht_score: str | None = None
    first_goal_team: str | None = None
    first_goal_player: str | None = None
    first_goal_minute: int | None = None
    first_goal_extra_minute: int | None = None
    goal_events: list[GoalEvent] = field(default_factory=list)
    outcome_source: str = "api-football"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "match_outcome_type": self.match_outcome_type,
            "ht_home_goals": self.ht_home_goals,
            "ht_away_goals": self.ht_away_goals,
            "ht_result": self.ht_result,
            "ht_score": self.ht_score,
            "first_goal_team": self.first_goal_team,
            "first_goal_player": self.first_goal_player,
            "first_goal_minute": self.first_goal_minute,
            "first_goal_extra_minute": self.first_goal_extra_minute,
            "goal_events": [e.to_dict() for e in self.goal_events],
            "outcome_source": self.outcome_source,
        }
