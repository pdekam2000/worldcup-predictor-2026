from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SelectionLevel = Literal[
    "AUTO_PREDICT",
    "WATCHLIST",
    "WAIT_FOR_LINEUPS",
    "SKIP_LOW_QUALITY",
    "SKIP_LOW_INTEREST",
]


@dataclass
class MatchSelectionScores:
    data_readiness_score: float = 0.0
    market_interest_score: float = 0.0
    odds_availability_score: float = 0.0
    model_confidence_score: float = 0.0
    historical_edge_score: float = 0.0
    team_importance_score: float = 0.0
    volatility_risk_score: float = 0.0
    lineup_proximity_score: float = 0.0

    @property
    def total(self) -> float:
        weights = {
            "data_readiness_score": 0.22,
            "market_interest_score": 0.12,
            "odds_availability_score": 0.12,
            "model_confidence_score": 0.18,
            "historical_edge_score": 0.12,
            "team_importance_score": 0.08,
            "lineup_proximity_score": 0.10,
            "volatility_risk_score": 0.06,
        }
        raw = sum(getattr(self, k) * w for k, w in weights.items())
        risk_penalty = self.volatility_risk_score * 0.06
        return round(max(0.0, min(100.0, raw - risk_penalty)), 2)

    def as_dict(self) -> dict[str, float]:
        return {
            "data_readiness_score": self.data_readiness_score,
            "market_interest_score": self.market_interest_score,
            "odds_availability_score": self.odds_availability_score,
            "model_confidence_score": self.model_confidence_score,
            "historical_edge_score": self.historical_edge_score,
            "team_importance_score": self.team_importance_score,
            "volatility_risk_score": self.volatility_risk_score,
            "lineup_proximity_score": self.lineup_proximity_score,
            "total_score": self.total,
        }


@dataclass
class MatchSelectionResult:
    fixture_id: int
    competition_key: str
    match_name: str
    kickoff_utc: str | None
    level: SelectionLevel
    scores: MatchSelectionScores
    reason: str
    expected_improvement: str = ""
    data_quality: float = 0.0
    lineups_available: bool = False
    hours_until_kickoff: float | None = None


@dataclass
class DailyShortlist:
    competition_key: str
    generated_at: str
    auto_predict: list[MatchSelectionResult] = field(default_factory=list)
    watchlist: list[MatchSelectionResult] = field(default_factory=list)
    wait_for_lineups: list[MatchSelectionResult] = field(default_factory=list)
    skipped: list[MatchSelectionResult] = field(default_factory=list)

    @property
    def total_upcoming(self) -> int:
        return (
            len(self.auto_predict)
            + len(self.watchlist)
            + len(self.wait_for_lineups)
            + len(self.skipped)
        )
