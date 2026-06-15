from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketPerformance:
    one_x_two_accuracy: float | None = None
    over_under_accuracy: float | None = None
    halftime_bucket_accuracy: float | None = None
    average_confidence: float = 0.0
    no_bet_rate: float | None = None
    sample_size: int = 0


@dataclass
class WeightSearchResult:
    weights: dict[str, float]
    score: float
    market_performance: MarketPerformance


@dataclass
class WeightTuningResult:
    best_weights_overall: dict[str, float]
    best_weights_1x2: dict[str, float]
    best_weights_over_under: dict[str, float]
    best_weights_halftime: dict[str, float]
    performance_before: MarketPerformance
    performance_after: MarketPerformance
    candidates_evaluated: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class ThresholdTuningResult:
    recommended_thresholds: dict[str, float]
    market_thresholds: dict[str, dict[str, float]]
    performance_before: MarketPerformance
    performance_after: MarketPerformance
    no_bet_rate_before: float | None = None
    no_bet_rate_after: float | None = None
    accuracy_before: float | None = None
    accuracy_after: float | None = None
    candidates_evaluated: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class CalibrationResult:
    csv_path: str
    sample_size: int
    is_demo_data: bool
    current_weights: dict[str, float]
    recommended_weights: dict[str, float]
    current_thresholds: dict[str, float]
    recommended_thresholds: dict[str, float]
    weight_tuning: WeightTuningResult
    threshold_tuning: ThresholdTuningResult
    market_comparison: dict[str, dict[str, Any]]
    sample_size_warning: str | None = None
    overfitting_warnings: list[str] = field(default_factory=list)
    disclaimers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "csv_path": self.csv_path,
            "sample_size": self.sample_size,
            "is_demo_data": self.is_demo_data,
            "current_weights": self.current_weights,
            "recommended_weights": self.recommended_weights,
            "current_thresholds": self.current_thresholds,
            "recommended_thresholds": self.recommended_thresholds,
            "weight_tuning": {
                "best_weights_overall": self.weight_tuning.best_weights_overall,
                "best_weights_1x2": self.weight_tuning.best_weights_1x2,
                "best_weights_over_under": self.weight_tuning.best_weights_over_under,
                "best_weights_halftime": self.weight_tuning.best_weights_halftime,
                "performance_before": _market_perf_dict(self.weight_tuning.performance_before),
                "performance_after": _market_perf_dict(self.weight_tuning.performance_after),
                "candidates_evaluated": self.weight_tuning.candidates_evaluated,
                "warnings": self.weight_tuning.warnings,
            },
            "threshold_tuning": {
                "recommended_thresholds": self.threshold_tuning.recommended_thresholds,
                "market_thresholds": self.threshold_tuning.market_thresholds,
                "performance_before": _market_perf_dict(self.threshold_tuning.performance_before),
                "performance_after": _market_perf_dict(self.threshold_tuning.performance_after),
                "no_bet_rate_before": self.threshold_tuning.no_bet_rate_before,
                "no_bet_rate_after": self.threshold_tuning.no_bet_rate_after,
                "accuracy_before": self.threshold_tuning.accuracy_before,
                "accuracy_after": self.threshold_tuning.accuracy_after,
                "candidates_evaluated": self.threshold_tuning.candidates_evaluated,
                "warnings": self.threshold_tuning.warnings,
            },
            "market_comparison": self.market_comparison,
            "sample_size_warning": self.sample_size_warning,
            "overfitting_warnings": self.overfitting_warnings,
            "disclaimers": self.disclaimers,
        }


def _market_perf_dict(perf: MarketPerformance) -> dict[str, Any]:
    return {
        "one_x_two_accuracy": perf.one_x_two_accuracy,
        "over_under_accuracy": perf.over_under_accuracy,
        "halftime_bucket_accuracy": perf.halftime_bucket_accuracy,
        "average_confidence": round(perf.average_confidence, 2),
        "no_bet_rate": perf.no_bet_rate,
        "sample_size": perf.sample_size,
    }
