from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from worldcup_predictor.adaptive_confidence.models import AdaptiveConfidenceAdjustment
    from worldcup_predictor.domain.audit import PredictionAuditReport

Locale = Literal["en", "de", "fa"]
RiskLevel = Literal["low", "medium", "high"]
OneXTwoSelection = Literal["home_win", "draw", "away_win"]
OverUnderSelection = Literal["over_2_5", "under_2_5"]


class ConfidenceLevel(str, Enum):
    """Qualitative confidence band — not a betting recommendation."""

    UNAVAILABLE = "unavailable"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class MultilingualText:
    """Localized strings keyed by locale code."""

    en: str
    de: str
    fa: str

    def get(self, locale: Locale) -> str:
        return getattr(self, locale, self.en)

    @classmethod
    def uniform(cls, text: str) -> "MultilingualText":
        return cls(en=text, de=text, fa=text)


@dataclass
class RiskProfile:
    """Mandatory risk disclosure — never present predictions as guaranteed outcomes."""

    risk_level: Literal["high", "medium", "informational"]
    warnings: MultilingualText
    disclaimer: MultilingualText


@dataclass
class PredictionPlaceholder:
    """
    Placeholder prediction envelope for Phase 1.
    Contains confidence metadata and risk warnings — no betting claims.
    """

    fixture_id: int
    competition_key: str
    confidence_score: float | None = None
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNAVAILABLE
    confidence_note: MultilingualText | None = None
    risk: RiskProfile | None = None
    summary: MultilingualText | None = None
    data_collected: bool = False
    model_ready: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Predictions are never actionable betting advice."""
        return False


@dataclass
class MarketPrediction:
    """Single market analytical selection — not a betting recommendation."""

    market: str
    selection: str
    probability: float | None = None
    label: MultilingualText | None = None


@dataclass
class ScorelineCandidate:
    home_goals: int
    away_goals: int
    probability: float

    @property
    def label(self) -> str:
        return f"{self.home_goals}-{self.away_goals}"

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals


@dataclass
class ScorelinePrediction:
    home_goals: float
    away_goals: float

    @property
    def label(self) -> str:
        return f"{round(self.home_goals)}-{round(self.away_goals)}"


@dataclass
class HalftimePrediction:
    estimated_total_goals: float
    note: MultilingualText | None = None


@dataclass
class FirstGoalScorerCandidate:
    player: str
    team: str
    score: float
    reason: str
    data_source: str


@dataclass
class FirstGoalPrediction:
    team: str
    player: str | None = None
    minute_range: str | None = None
    scorer_candidates: list[FirstGoalScorerCandidate] = field(default_factory=list)
    player_data_unavailable: bool = False
    player_data_message: str | None = None


@dataclass
class PredictionReason:
    key: str
    weight: float
    description: MultilingualText


@dataclass
class PredictionRiskWarning:
    level: RiskLevel
    messages: MultilingualText


@dataclass
class PredictionConfidenceBreakdown:
    form_score: float
    h2h_score: float
    injuries_score: float
    lineups_score: float
    odds_score: float
    data_quality_score: float
    total: float


@dataclass
class MatchPrediction:
    """
    Structured analytical match prediction — Phase 3.
    Not guaranteed; not financial or betting advice.
    """

    fixture_id: int
    competition_key: str
    match_name: str
    one_x_two: MarketPrediction
    over_under: MarketPrediction
    halftime: HalftimePrediction
    first_goal: FirstGoalPrediction
    confidence_score: float
    confidence_level: ConfidenceLevel
    confidence_breakdown: PredictionConfidenceBreakdown
    risk_level: RiskLevel
    risk_warnings: list[PredictionRiskWarning] = field(default_factory=list)
    no_bet_flag: bool = True
    explanation: MultilingualText | None = None
    disclaimer: MultilingualText | None = None
    missing_data_warnings: MultilingualText | None = None
    lineup_warning: MultilingualText | None = None
    scoreline: ScorelinePrediction | None = None
    scoreline_candidates: list[ScorelineCandidate] = field(default_factory=list)
    prediction_quality_score: float = 0.0
    consistency_notes: list[str] = field(default_factory=list)
    group_context: dict[str, Any] | None = None
    reasons: list[PredictionReason] = field(default_factory=list)
    kickoff_utc: datetime | None = None
    stage: str | None = None
    is_placeholder: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    audit_report: "PredictionAuditReport | None" = None
    first_goal_player_confidence: float | None = None
    adaptive_confidence: "AdaptiveConfidenceAdjustment | None" = None

    @property
    def is_actionable(self) -> bool:
        """Analytical only — never actionable betting advice."""
        return False
