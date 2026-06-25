"""Provider utilization data models — Phase 46D."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EventType = Literal[
    "goal",
    "own_goal",
    "penalty_goal",
    "card",
    "substitution",
    "assist",
    "other",
]

ProviderSource = Literal["api-football", "sportmonks", "cache", "merged"]


@dataclass(frozen=True)
class UnifiedMatchEvent:
    sort_index: int
    event_type: EventType
    minute: int | None
    extra_minute: int | None
    team: str | None
    team_id: int | None
    player: str | None
    assist: str | None
    detail: str | None
    source: ProviderSource
    is_penalty: bool = False
    is_own_goal: bool = False
    card_type: str | None = None
    sub_in: str | None = None
    sub_out: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedEventLayerResult:
    fixture_id: int
    events: list[UnifiedMatchEvent] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    merge_policy: str = "api_football_primary"
    goal_count: int = 0
    card_count: int = 0
    substitution_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "events": [e.to_dict() for e in self.events],
            "sources_used": self.sources_used,
            "merge_policy": self.merge_policy,
            "goal_count": self.goal_count,
            "card_count": self.card_count,
            "substitution_count": self.substitution_count,
        }


@dataclass
class OddsMovementIntelligence:
    odds_movement_score: float
    odds_movement_direction: str | None
    market_confidence_shift: float
    opening_implied_home: float | None = None
    current_implied_home: float | None = None
    implied_probability_delta_home: float | None = None
    sharp_movement_detected: bool = False
    consensus_drift: str | None = None
    bookmaker_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdvancedMatchIntelligence:
    attacking_edge_home: float | None = None
    attacking_edge_away: float | None = None
    defensive_edge_home: float | None = None
    defensive_edge_away: float | None = None
    xg_home: float | None = None
    xg_away: float | None = None
    xga_home: float | None = None
    xga_away: float | None = None
    xg_momentum: float | None = None
    expected_scoring_pressure: float | None = None
    shot_quality_home: float | None = None
    shot_quality_away: float | None = None
    attack_efficiency_home: float | None = None
    attack_efficiency_away: float | None = None
    defensive_efficiency_home: float | None = None
    defensive_efficiency_away: float | None = None
    source: str = "sportmonks"
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerIntelligenceProfile:
    player: str
    team: str | None = None
    recent_goals: int = 0
    recent_assists: int = 0
    form_score: float | None = None
    minutes_played: int | None = None
    available: bool = True
    lineup_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlayerIntelligenceResult:
    fixture_id: int
    profiles: list[PlayerIntelligenceProfile] = field(default_factory=list)
    top_scorer_candidate: str | None = None
    first_goal_candidate: str | None = None
    first_goal_team_hint: str | None = None
    goalscorer_confidence: float | None = None
    sources_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "profiles": [p.to_dict() for p in self.profiles],
            "top_scorer_candidate": self.top_scorer_candidate,
            "first_goal_candidate": self.first_goal_candidate,
            "first_goal_team_hint": self.first_goal_team_hint,
            "goalscorer_confidence": self.goalscorer_confidence,
            "sources_used": self.sources_used,
        }


@dataclass
class ProviderUtilizationBundle:
    fixture_id: int
    version: str = "46d_v1"
    unified_events: UnifiedEventLayerResult | None = None
    odds_movement: OddsMovementIntelligence | None = None
    advanced_match: AdvancedMatchIntelligence | None = None
    player_intelligence: PlayerIntelligenceResult | None = None
    fusion_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "version": self.version,
            "unified_events": self.unified_events.to_dict() if self.unified_events else None,
            "odds_movement": self.odds_movement.to_dict() if self.odds_movement else None,
            "advanced_match": self.advanced_match.to_dict() if self.advanced_match else None,
            "player_intelligence": self.player_intelligence.to_dict() if self.player_intelligence else None,
            "fusion_notes": self.fusion_notes,
        }
