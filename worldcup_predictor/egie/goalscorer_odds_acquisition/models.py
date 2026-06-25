"""Phase 54N goalscorer odds acquisition models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MarketKind = Literal["player_goalscorer", "team_goalscorer", "player_goalscorer_team_scoped", "other_goalscorer_related"]

VALID_RECOMMENDATIONS = frozenset(
    {
        "GOALSCORER_ODDS_EXPAND",
        "GOALSCORER_ODDS_LIMITED",
        "GOALSCORER_ODDS_NOT_WORTH_IT",
    }
)

PRIORITY_LEAGUES: dict[int, str] = {
    732: "world_cup",
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
}


@dataclass
class SourceInventory:
    source: str
    fixtures_audited: int = 0
    fixtures_with_goalscorer_odds: int = 0
    selection_count: int = 0
    market_count: int = 0
    bookmaker_count: int = 0
    notes: str = ""
    markets: dict[str, int] = field(default_factory=dict)
    bookmakers: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateFixture:
    fixture_id: int
    source: str
    league: str
    season: str | int | None
    date: str | None
    bookmaker: str
    market_count: int
    selection_count: int
    priority_score: int = 0
    has_lineups: bool = False
    finished: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketSplitSummary:
    player_goalscorer_rows: int = 0
    team_goalscorer_rows: int = 0
    player_team_scoped_rows: int = 0
    other_rows: int = 0
    total_rows: int = 0
    by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    by_market: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MappingReadinessProjection:
    fixture_count: int
    expected_selections: int
    expected_mapped_player_rows: int
    expected_mapping_rate: float
    assumptions: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BackfillPlan:
    strategy: str
    candidate_fixtures: int
    expected_api_calls: int
    expected_odds_fixtures: int
    expected_player_selections: int
    quota_impact: str
    steps: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
