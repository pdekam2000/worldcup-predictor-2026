from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PredictionVersion = Literal["early_24h", "pre_6h", "final_lineup", "manual"]


@dataclass
class PredictionHistoryRecord:
    fixture_id: int
    date: str
    home_team: str
    away_team: str
    predicted_1x2: str
    predicted_over_under_2_5: str
    predicted_halftime_goals: float
    predicted_first_goal_team: str
    confidence_score: float
    risk_level: str
    no_bet_flag: bool
    data_quality_score: float
    source: str
    created_at: str
    prediction_id: str = ""
    prediction_version: PredictionVersion = "manual"
    refreshed_from_prediction_id: str | None = None
    reason_for_refresh: str | None = None
    lineups_available: bool = False
    is_preliminary: bool = True
    predicted_scoreline: str | None = None
    predicted_first_goal_scorer: str | None = None
    extended_markets_json: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PredictionHistoryRecord:
        fixture_id = int(data["fixture_id"])
        return cls(
            fixture_id=fixture_id,
            date=str(data["date"]),
            home_team=str(data["home_team"]),
            away_team=str(data["away_team"]),
            predicted_1x2=str(data["predicted_1x2"]),
            predicted_over_under_2_5=str(data["predicted_over_under_2_5"]),
            predicted_halftime_goals=float(data["predicted_halftime_goals"]),
            predicted_first_goal_team=str(data["predicted_first_goal_team"]),
            confidence_score=float(data["confidence_score"]),
            risk_level=str(data["risk_level"]),
            no_bet_flag=bool(data["no_bet_flag"]),
            data_quality_score=float(data["data_quality_score"]),
            source=str(data["source"]),
            created_at=str(data["created_at"]),
            prediction_id=str(data.get("prediction_id") or f"legacy-{fixture_id}"),
            prediction_version=data.get("prediction_version", "manual"),  # type: ignore[arg-type]
            refreshed_from_prediction_id=data.get("refreshed_from_prediction_id"),
            reason_for_refresh=data.get("reason_for_refresh"),
            lineups_available=bool(data.get("lineups_available", False)),
            is_preliminary=bool(data.get("is_preliminary", True)),
            predicted_scoreline=data.get("predicted_scoreline"),
            predicted_first_goal_scorer=data.get("predicted_first_goal_scorer"),
            extended_markets_json=data.get("extended_markets_json"),
        )


@dataclass
class EvaluatedPrediction:
    fixture_id: int
    match_name: str
    date: str
    home_team: str
    away_team: str
    predicted_1x2: str
    actual_1x2: str
    one_x_two_correct: bool
    predicted_over_under: str
    actual_over_under: str
    over_under_correct: bool
    predicted_halftime_bucket: str | None
    actual_halftime_bucket: str | None
    halftime_bucket_correct: bool | None
    halftime_evaluated: bool
    first_goal_skipped: bool
    confidence_score: float
    no_bet_flag: bool
    data_quality_score: float
    source: str
    prediction_created_at: str
    evaluated_at: str
    final_score: str | None = None
    predicted_scoreline: str | None = None
    actual_scoreline: str | None = None
    scoreline_exact_correct: bool | None = None
    predicted_first_goal_team: str | None = None
    actual_first_goal_team: str | None = None
    first_goal_correct: bool | None = None
    first_goal_evaluated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluatedPrediction:
        return cls(
            fixture_id=int(data["fixture_id"]),
            match_name=str(data["match_name"]),
            date=str(data["date"]),
            home_team=str(data["home_team"]),
            away_team=str(data["away_team"]),
            predicted_1x2=str(data["predicted_1x2"]),
            actual_1x2=str(data["actual_1x2"]),
            one_x_two_correct=bool(data["one_x_two_correct"]),
            predicted_over_under=str(data["predicted_over_under"]),
            actual_over_under=str(data["actual_over_under"]),
            over_under_correct=bool(data["over_under_correct"]),
            predicted_halftime_bucket=data.get("predicted_halftime_bucket"),
            actual_halftime_bucket=data.get("actual_halftime_bucket"),
            halftime_bucket_correct=data.get("halftime_bucket_correct"),
            halftime_evaluated=bool(data.get("halftime_evaluated", False)),
            first_goal_skipped=bool(data.get("first_goal_skipped", True)),
            confidence_score=float(data["confidence_score"]),
            no_bet_flag=bool(data["no_bet_flag"]),
            data_quality_score=float(data.get("data_quality_score", 0.0)),
            source=str(data.get("source", "unknown")),
            prediction_created_at=str(data["prediction_created_at"]),
            evaluated_at=str(data["evaluated_at"]),
            final_score=data.get("final_score"),
            predicted_scoreline=data.get("predicted_scoreline"),
            actual_scoreline=data.get("actual_scoreline"),
            scoreline_exact_correct=data.get("scoreline_exact_correct"),
            predicted_first_goal_team=data.get("predicted_first_goal_team"),
            actual_first_goal_team=data.get("actual_first_goal_team"),
            first_goal_correct=data.get("first_goal_correct"),
            first_goal_evaluated=bool(data.get("first_goal_evaluated", False)),
        )


@dataclass
class ConfidenceRangeMetrics:
    label: str
    count: int = 0
    one_x_two_correct: int = 0
    over_under_correct: int = 0
    average_confidence: float = 0.0

    @property
    def one_x_two_accuracy(self) -> float | None:
        if self.count == 0:
            return None
        return round(self.one_x_two_correct / self.count, 4)

    @property
    def over_under_accuracy(self) -> float | None:
        if self.count == 0:
            return None
        return round(self.over_under_correct / self.count, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "count": self.count,
            "one_x_two_accuracy": self.one_x_two_accuracy,
            "over_under_accuracy": self.over_under_accuracy,
            "average_confidence": round(self.average_confidence, 2),
        }


@dataclass
class AccuracySummaryMetrics:
    total_evaluated: int = 0
    one_x_two_accuracy: float | None = None
    over_under_2_5_accuracy: float | None = None
    halftime_bucket_accuracy: float | None = None
    halftime_evaluated_count: int = 0
    scoreline_exact_accuracy: float | None = None
    scoreline_evaluated_count: int = 0
    first_goal_accuracy: float | None = None
    first_goal_evaluated_count: int = 0
    total_predictions: int = 0
    model_grade: str = "—"
    best_market: str | None = None
    worst_market: str | None = None
    average_confidence: float = 0.0
    no_bet_count: int = 0
    no_bet_one_x_two_accuracy: float | None = None
    non_no_bet_one_x_two_accuracy: float | None = None
    no_bet_over_under_accuracy: float | None = None
    non_no_bet_over_under_accuracy: float | None = None
    confidence_buckets: list[ConfidenceRangeMetrics] = field(default_factory=list)
    best_confidence_range: str | None = None
    worst_confidence_range: str | None = None
    pending_predictions: int = 0
    first_goal_skipped_count: int = 0
    data_limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_evaluated": self.total_evaluated,
            "one_x_two_accuracy": self.one_x_two_accuracy,
            "over_under_2_5_accuracy": self.over_under_2_5_accuracy,
            "halftime_bucket_accuracy": self.halftime_bucket_accuracy,
            "halftime_evaluated_count": self.halftime_evaluated_count,
            "scoreline_exact_accuracy": self.scoreline_exact_accuracy,
            "scoreline_evaluated_count": self.scoreline_evaluated_count,
            "first_goal_accuracy": self.first_goal_accuracy,
            "first_goal_evaluated_count": self.first_goal_evaluated_count,
            "total_predictions": self.total_predictions,
            "model_grade": self.model_grade,
            "best_market": self.best_market,
            "worst_market": self.worst_market,
            "average_confidence": round(self.average_confidence, 2),
            "no_bet_count": self.no_bet_count,
            "no_bet_one_x_two_accuracy": self.no_bet_one_x_two_accuracy,
            "non_no_bet_one_x_two_accuracy": self.non_no_bet_one_x_two_accuracy,
            "no_bet_over_under_accuracy": self.no_bet_over_under_accuracy,
            "non_no_bet_over_under_accuracy": self.non_no_bet_over_under_accuracy,
            "confidence_buckets": [b.to_dict() for b in self.confidence_buckets],
            "best_confidence_range": self.best_confidence_range,
            "worst_confidence_range": self.worst_confidence_range,
            "pending_predictions": self.pending_predictions,
            "first_goal_skipped_count": self.first_goal_skipped_count,
            "data_limitations": self.data_limitations,
            "disclaimer": (
                "Historical model evaluation does not guarantee future results. "
                "Accuracy tracking is for calibration and learning memory only — not profit or betting advice."
            ),
        }
