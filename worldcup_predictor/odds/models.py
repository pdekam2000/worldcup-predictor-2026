"""Dataclasses for Phase 36 odds and league learning signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

AgreementLevel = Literal["high", "medium", "low", "unknown"]


@dataclass
class MarketConsensusSignal:
    market_favorite: str
    home_implied_probability: float | None
    draw_implied_probability: float | None
    away_implied_probability: float | None
    over_2_5_probability: float | None
    under_2_5_probability: float | None
    consensus_strength: float
    bookmaker_disagreement_score: float
    model_market_agreement: AgreementLevel
    market_supports_model: bool | None
    disagreement_warning: bool
    average_home_odds: float | None = None
    average_draw_odds: float | None = None
    average_away_odds: float | None = None
    market_confidence_score: float = 0.0
    sources_used: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    informational_disclaimer: str = "Market consensus is analytical only — not betting advice."
    bookmaker_count_1x2: int = 0
    bookmaker_count_ou25: int = 0
    used_bookmakers: list[str] = field(default_factory=list)
    skipped_bookmakers: list[str] = field(default_factory=list)
    aggregation_method: str = "multi_bookmaker_average"
    bookmaker_disagreement_level: str = "unknown"
    bookmaker_disagreement_level_ou25: str = "unknown"
    bookmaker_std_dev_1x2: float = 0.0
    bookmaker_std_dev_ou25: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OddsMovementSignal:
    home_movement: float | None
    draw_movement: float | None
    away_movement: float | None
    over_movement: float | None
    under_movement: float | None
    strongest_move: str | None
    movement_confidence: float
    warning: str | None
    opening_home_odds: float | None = None
    latest_home_odds: float | None = None
    opening_draw_odds: float | None = None
    latest_draw_odds: float | None = None
    opening_away_odds: float | None = None
    latest_away_odds: float | None = None
    steam_move_detected: bool = False
    suspicious_volatility: bool = False
    market_drift: str | None = None
    snapshot_count: int = 0
    notes: list[str] = field(default_factory=list)
    informational_disclaimer: str = "Odds movement is informational only — not betting advice."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutcomeOddsTrack:
    opening_odds: float | None
    latest_odds: float | None
    movement_pct: float | None
    movement_direction: str | None
    movement_class: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OddsSnapshotTrack:
    home: OutcomeOddsTrack
    draw: OutcomeOddsTrack
    away: OutcomeOddsTrack
    over_2_5: OutcomeOddsTrack
    under_2_5: OutcomeOddsTrack
    snapshot_count: int = 0
    history_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home.to_dict(),
            "draw": self.draw.to_dict(),
            "away": self.away.to_dict(),
            "over_2_5": self.over_2_5.to_dict(),
            "under_2_5": self.under_2_5.to_dict(),
            "snapshot_count": self.snapshot_count,
            "history_available": self.history_available,
        }


@dataclass
class SharpMoneyPredictionImpact:
    home_adjustment: float = 0.0
    away_adjustment: float = 0.0
    draw_adjustment: float = 0.0
    over25_adjustment: float = 0.0
    under25_adjustment: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class SharpMoneyIntelligenceResult:
    odds_tracking: OddsSnapshotTrack
    sharp_money_score: float
    sharp_money_band: str
    reverse_line_movement: bool
    reverse_line_confidence: float
    consensus_strength: float
    disagreement_level: str
    probability_dispersion: float
    over_market_bias: float
    under_market_bias: float
    goals_market_confidence: float
    market_confidence: float
    steam_move_detected: bool
    movement_summary: str
    risk_flags: list[str]
    prediction_impact: SharpMoneyPredictionImpact
    summary: str
    bookmaker_count_1x2: int = 0
    bookmaker_count_ou25: int = 0
    version: str = "v2"

    def to_dict(self) -> dict[str, Any]:
        return {
            "odds_tracking": self.odds_tracking.to_dict(),
            "sharp_money_score": self.sharp_money_score,
            "sharp_money_band": self.sharp_money_band,
            "reverse_line_movement": self.reverse_line_movement,
            "reverse_line_confidence": self.reverse_line_confidence,
            "consensus_strength": self.consensus_strength,
            "disagreement_level": self.disagreement_level,
            "probability_dispersion": self.probability_dispersion,
            "over_market_bias": self.over_market_bias,
            "under_market_bias": self.under_market_bias,
            "goals_market_confidence": self.goals_market_confidence,
            "market_confidence": self.market_confidence,
            "steam_move_detected": self.steam_move_detected,
            "movement_summary": self.movement_summary,
            "risk_flags": self.risk_flags,
            "prediction_impact": self.prediction_impact.to_dict(),
            "summary": self.summary,
            "bookmaker_count_1x2": self.bookmaker_count_1x2,
            "bookmaker_count_ou25": self.bookmaker_count_ou25,
            "version": self.version,
        }


@dataclass
class LeagueLearningProfile:
    competition_key: str
    competition_name: str
    evaluated_matches: int
    strongest_market: str | None
    weakest_market: str | None
    market_winrates: dict[str, float | None]
    confidence_reliability: dict[str, float | None]
    data_quality_reliability: dict[str, float | None]
    recommended_rules: list[str]
    recommended_confidence_thresholds: dict[str, float]
    sample_size_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
