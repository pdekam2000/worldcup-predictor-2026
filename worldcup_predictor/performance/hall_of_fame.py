"""Prediction Accuracy Hall of Fame — read-only trust metrics (no prediction impact)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.accuracy.metrics import compute_accuracy_metrics
from worldcup_predictor.accuracy.models import EvaluatedPrediction
from worldcup_predictor.accuracy.service import AccuracyTrackerService
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.learning.self_learning_engine_v2 import build_self_learning_report
from worldcup_predictor.learning.self_learning_models import (
    AgentPerformanceMetrics,
    CalibrationBucket,
    LeaguePerformanceMetrics,
)


def _parse_ts(item: EvaluatedPrediction) -> datetime:
    raw = item.evaluated_at or item.prediction_created_at or item.date
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw)[:26], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _draw_accuracy(evaluated: list[EvaluatedPrediction]) -> float | None:
    draws = [item for item in evaluated if item.predicted_1x2 == "draw"]
    if not draws:
        return None
    hits = sum(1 for item in draws if item.one_x_two_correct)
    return round(hits / len(draws), 4)


@dataclass
class HallOfFameWindow:
    label: str
    verified: int = 0
    one_x_two_accuracy: float | None = None
    over_under_accuracy: float | None = None
    draw_accuracy: float | None = None
    average_confidence: float = 0.0
    model_grade: str = "—"
    best_confidence_range: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HallOfFameReport:
    total_predictions: int = 0
    verified_predictions: int = 0
    pending_predictions: int = 0
    all_time: HallOfFameWindow = field(default_factory=lambda: HallOfFameWindow(label="all_time"))
    last_30_days: HallOfFameWindow = field(default_factory=lambda: HallOfFameWindow(label="last_30_days"))
    last_100: HallOfFameWindow = field(default_factory=lambda: HallOfFameWindow(label="last_100"))
    calibration_buckets: list[CalibrationBucket] = field(default_factory=list)
    best_tournaments: list[LeaguePerformanceMetrics] = field(default_factory=list)
    best_agents: list[AgentPerformanceMetrics] = field(default_factory=list)
    data_limitations: list[str] = field(default_factory=list)
    disclaimer: str = (
        "Hall of Fame statistics reflect verified historical predictions only. "
        "Past accuracy does not guarantee future results — not betting advice."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_predictions": self.total_predictions,
            "verified_predictions": self.verified_predictions,
            "pending_predictions": self.pending_predictions,
            "all_time": self.all_time.to_dict(),
            "last_30_days": self.last_30_days.to_dict(),
            "last_100": self.last_100.to_dict(),
            "calibration_buckets": [b.to_dict() for b in self.calibration_buckets],
            "best_tournaments": [t.to_dict() for t in self.best_tournaments],
            "best_agents": [a.to_dict() for a in self.best_agents],
            "data_limitations": list(self.data_limitations),
            "disclaimer": self.disclaimer,
        }


def _window_from_evaluated(evaluated: list[EvaluatedPrediction], label: str) -> HallOfFameWindow:
    if not evaluated:
        return HallOfFameWindow(label=label)
    metrics = compute_accuracy_metrics(evaluated, total_predictions=len(evaluated))
    return HallOfFameWindow(
        label=label,
        verified=len(evaluated),
        one_x_two_accuracy=metrics.one_x_two_accuracy,
        over_under_accuracy=metrics.over_under_2_5_accuracy,
        draw_accuracy=_draw_accuracy(evaluated),
        average_confidence=metrics.average_confidence,
        model_grade=metrics.model_grade,
        best_confidence_range=metrics.best_confidence_range,
    )


def build_hall_of_fame_report(
    *,
    settings: Settings | None = None,
    competition_key: str | None = None,
) -> HallOfFameReport:
    """Build read-only Hall of Fame report from stored accuracy + learning memory."""
    active_settings = settings or get_settings()
    comp = competition_key or "world_cup_2026"
    svc = AccuracyTrackerService(active_settings, competition_key=comp)
    snapshot = svc.load_summary_from_disk()
    learning = build_self_learning_report(competition_key=comp)

    if snapshot is None:
        return HallOfFameReport(
            total_predictions=learning.total_records,
            verified_predictions=learning.verified_records,
            pending_predictions=learning.pending_records,
            calibration_buckets=learning.calibration_buckets,
            best_tournaments=learning.league_rankings[:5],
            best_agents=learning.agent_rankings[:8],
            data_limitations=[
                "No evaluated prediction history on disk yet.",
                "Predict matches before kickoff, then wait for results to build the Hall of Fame.",
            ],
        )

    evaluated = list(snapshot.evaluated)
    evaluated.sort(key=_parse_ts, reverse=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    last_30 = [item for item in evaluated if _parse_ts(item) >= cutoff]
    last_100 = evaluated[:100]

    metrics = snapshot.metrics
    limitations = list(metrics.data_limitations or [])
    if len(evaluated) < 10:
        limitations.append("Small sample size — interpret win rates with caution.")

    return HallOfFameReport(
        total_predictions=metrics.total_predictions,
        verified_predictions=metrics.total_evaluated,
        pending_predictions=metrics.pending_predictions,
        all_time=_window_from_evaluated(evaluated, "all_time"),
        last_30_days=_window_from_evaluated(last_30, "last_30_days"),
        last_100=_window_from_evaluated(last_100, "last_100"),
        calibration_buckets=learning.calibration_buckets,
        best_tournaments=learning.league_rankings[:5],
        best_agents=learning.agent_rankings[:8],
        data_limitations=limitations,
    )
