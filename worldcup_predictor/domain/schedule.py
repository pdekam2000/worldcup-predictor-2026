from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

QualificationStatus = Literal[
    "unknown",
    "likely_qualified",
    "must_win",
    "eliminated",
    "rotation_risk",
]
ScheduleSource = Literal["live", "cache", "placeholder"]


@dataclass
class GroupStanding:
    group_name: str
    team_name: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0
    qualification_status: QualificationStatus = "unknown"
    rank: int = 0
    is_placeholder: bool = True


@dataclass
class WorldCupGroup:
    group_name: str
    standings: list[GroupStanding] = field(default_factory=list)
    is_placeholder: bool = True
    source: ScheduleSource = "placeholder"
    disclaimer: str = "Placeholder group table — not official or confirmed."


@dataclass
class TournamentFixture:
    fixture_id: int
    kickoff_time: datetime
    home_team: str
    away_team: str
    venue: str
    city: str
    country: str
    group: str
    round: str
    status: str = "NS"
    is_placeholder: bool = True
    source: ScheduleSource = "placeholder"
    home_goals: int | None = None
    away_goals: int | None = None
    halftime_home_goals: int | None = None
    halftime_away_goals: int | None = None
    elapsed_minute: int | None = None
    red_cards_home: int = 0
    red_cards_away: int = 0
    goal_scorers: list[str] = field(default_factory=list)
    stats_summary: dict[str, str] = field(default_factory=dict)
    home_team_logo: str | None = None
    away_team_logo: str | None = None


@dataclass
class ScheduleHealthReport:
    source: ScheduleSource = "placeholder"
    is_placeholder: bool = True
    warnings: list[str] = field(default_factory=list)
    fixtures_count: int = 0
    standings_available: bool = False
    groups_available: bool = False
    api_configured: bool = False


@dataclass
class UpcomingMatchWindow:
    fixtures: list[TournamentFixture] = field(default_factory=list)
    analysis_readiness_score: float = 0.0
    analysis_ready: bool = False
    warnings: list[str] = field(default_factory=list)
    is_placeholder: bool = True
    note: str = "Analysis readiness window — not a betting recommendation."


@dataclass
class TournamentOverview:
    fixtures: list[TournamentFixture] = field(default_factory=list)
    groups: dict[str, WorldCupGroup] = field(default_factory=dict)
    health: ScheduleHealthReport = field(default_factory=ScheduleHealthReport)
    upcoming: list[TournamentFixture] = field(default_factory=list)

    def context_for_fixture(self, fixture_id: int) -> dict[str, object]:
        """Tournament context for a single fixture (group pressure, motivation)."""
        fixture = next((f for f in self.fixtures if f.fixture_id == fixture_id), None)
        if fixture is None:
            return {}

        group = self.groups.get(fixture.group)
        home_standing = self._standing(group, fixture.home_team)
        away_standing = self._standing(group, fixture.away_team)

        return {
            "group": fixture.group,
            "round": fixture.round,
            "home_qualification_status": home_standing.qualification_status if home_standing else "unknown",
            "away_qualification_status": away_standing.qualification_status if away_standing else "unknown",
            "home_points": home_standing.points if home_standing else 0,
            "away_points": away_standing.points if away_standing else 0,
            "home_goal_difference": home_standing.goal_difference if home_standing else 0,
            "away_goal_difference": away_standing.goal_difference if away_standing else 0,
            "is_placeholder": self.health.is_placeholder,
            "match_importance": self._match_importance(home_standing, away_standing),
        }

    @staticmethod
    def _standing(group: WorldCupGroup | None, team_name: str) -> GroupStanding | None:
        if group is None:
            return None
        for row in group.standings:
            if row.team_name.lower() == team_name.lower():
                return row
        return None

    @staticmethod
    def _match_importance(
        home: GroupStanding | None,
        away: GroupStanding | None,
    ) -> str:
        statuses = {s.qualification_status for s in (home, away) if s}
        if "must_win" in statuses or "eliminated" in statuses:
            return "high"
        if "rotation_risk" in statuses or "likely_qualified" in statuses:
            return "moderate"
        return "standard"
