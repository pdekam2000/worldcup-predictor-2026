from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from worldcup_predictor.domain.fixture import Fixture

SourceKind = Literal["live", "cache", "placeholder"]


@dataclass
class InjuryReport:
    team_name: str
    team_id: int | None
    players: list[dict[str, Any]] = field(default_factory=list)
    source: SourceKind = "placeholder"
    available: bool = False
    error: str | None = None


@dataclass
class OddsSnapshot:
    """
    Raw odds data snapshot for analysis context only.
    Not a betting recommendation.
    """

    fixture_id: int
    bookmakers: list[dict[str, Any]] = field(default_factory=list)
    source: SourceKind = "placeholder"
    available: bool = False
    error: str | None = None
    note: str = "Informational odds snapshot — not betting advice"


@dataclass
class TeamIntelligence:
    team_name: str
    team_id: int | None = None
    form: list[str] | None = None
    statistics: dict[str, Any] | None = None
    injuries: InjuryReport | None = None
    source: SourceKind = "placeholder"


@dataclass
class DataQualityReport:
    score: float
    available_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    breakdown: dict[str, int] = field(default_factory=dict)
    breakdown_total: int = 0
    breakdown_max: int = 100
    component_max: dict[str, int] = field(default_factory=dict)
    pre_match_data_quality: int = 0
    live_data_quality: int = 0
    post_match_data_quality: int = 0
    match_phase: str = "pre_match"
    reason_text: str = ""
    kickoff_note: str = ""

    @property
    def grade(self) -> str:
        if self.score >= 0.85:
            return "excellent"
        if self.score >= 0.65:
            return "good"
        if self.score >= 0.40:
            return "partial"
        return "minimal"


@dataclass
class EndpointInspection:
    endpoint: str
    loaded: bool
    response_count: int = 0
    source: str = "placeholder"
    error: str | None = None
    status: str = "unavailable"

    @property
    def status_label(self) -> str:
        return self.status


@dataclass
class ApiInspectionReport:
    endpoints: list[EndpointInspection] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            ep.endpoint: {
                "status": ep.status,
                "loaded": ep.loaded,
                "response_count": ep.response_count,
                "source": ep.source,
                "error": ep.error,
            }
            for ep in self.endpoints
        }


@dataclass
class MatchIntelligenceReport:
    fixture_id: int
    fixture: Fixture | None
    home_team: TeamIntelligence
    away_team: TeamIntelligence
    head_to_head: dict[str, Any] | None = None
    fixture_events: list[dict[str, Any]] | None = None
    fixture_statistics: dict[str, Any] | None = None
    lineups: dict[str, Any] | None = None
    odds: OddsSnapshot | None = None
    missing_data: list[str] = field(default_factory=list)
    data_quality: DataQualityReport | None = None
    source: SourceKind = "placeholder"
    is_placeholder: bool = True
    specialist_report: "MatchSpecialistReport | None" = None
    standings_context: dict[str, Any] | None = None
    home_recent_fixtures: list[dict[str, Any]] | None = None
    away_recent_fixtures: list[dict[str, Any]] | None = None
    weather: dict[str, Any] | None = None
    referee: str | None = None
    api_inspection: ApiInspectionReport | None = None
    group_context: dict[str, Any] | None = None
    enrichment_sources: list[str] = field(default_factory=list)
    supplemental_sources: dict[str, Any] = field(default_factory=dict)
    provider_metadata: dict[str, Any] | None = None

    @property
    def ready_for_prediction(self) -> bool:
        if self.data_quality is None:
            return False
        return self.data_quality.score >= 0.65 and not self.is_placeholder
