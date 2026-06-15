from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Fixture:
    """Normalized match fixture from any data provider."""

    id: int
    competition_key: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    venue: str
    stage: str
    league_id: int
    season: int
    status: str = "NS"
    source: str = "placeholder"
    home_team_id: int | None = None
    away_team_id: int | None = None
    referee: str | None = None

    @property
    def display_match(self) -> str:
        return f"{self.home_team} vs {self.away_team}"


@dataclass
class FixtureCollection:
    """Batch of fixtures with provider metadata."""

    fixtures: list[Fixture] = field(default_factory=list)
    competition_key: str = "world_cup_2026"
    source: str = "placeholder"
    is_placeholder: bool = True

    def upcoming(self, limit: int = 5) -> list[Fixture]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        sorted_fixtures = sorted(
            self.fixtures,
            key=lambda f: f.kickoff_utc,
        )
        return [f for f in sorted_fixtures if f.kickoff_utc >= now][:limit]
