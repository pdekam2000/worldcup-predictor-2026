from __future__ import annotations

import itertools
from pathlib import Path

from worldcup_predictor.calibration.evaluator import CalibrationEvaluator, overall_score
from worldcup_predictor.calibration.models import MarketPerformance, ThresholdTuningResult
from worldcup_predictor.config.model_weights import DEFAULT_THRESHOLDS, get_thresholds
from worldcup_predictor.config.settings import Settings, get_settings

SMALL_SAMPLE_THRESHOLD = 100


class ThresholdTuner:
    """Search confidence / no-bet threshold combinations on historical data."""

    THRESHOLD_KEYS = (
        "analysis_ready_confidence_minimum",
        "no_bet_confidence_minimum",
        "data_quality_cap_value",
        "missing_lineups_first_goal_cap",
        "specialist_conflict_penalty_per_conflict",
    )

    GRID: dict[str, list[float]] = {
        "analysis_ready_confidence_minimum": [55.0, 60.0, 65.0],
        "no_bet_confidence_minimum": [55.0, 60.0, 65.0],
        "data_quality_cap_value": [40.0, 45.0, 50.0],
        "missing_lineups_first_goal_cap": [25.0, 30.0, 35.0],
        "specialist_conflict_penalty_per_conflict": [3.0, 4.0, 5.0],
    }

    def __init__(self, settings: Settings | None = None, *, locale: str = "en") -> None:
        self._settings = settings or get_settings()
        self._locale = locale

    def tune(
        self,
        csv_path: Path | str,
        *,
        factor_weights: dict[str, float] | None = None,
        evaluator: CalibrationEvaluator | None = None,
    ) -> ThresholdTuningResult:
        from worldcup_predictor.config.model_weights import get_factor_weights

        active_evaluator = evaluator or CalibrationEvaluator(
            csv_path, self._settings, locale=self._locale
        )
        weights = factor_weights or get_factor_weights(use_calibrated=False)
        base_thresholds = get_thresholds(use_calibrated=False)

        _, before = active_evaluator.evaluate(weights, base_thresholds)
        candidates = _generate_threshold_candidates(base_thresholds)
        warnings = _sample_warnings(active_evaluator.sample_size, len(candidates))

        best_thresholds = dict(base_thresholds)
        best_score = _threshold_objective(before)
        best_perf = before

        for candidate in candidates:
            _, perf = active_evaluator.evaluate(weights, candidate)
            score = _threshold_objective(perf)
            if score > best_score:
                best_score = score
                best_thresholds = candidate
                best_perf = perf

        market_thresholds = {
            "1x2": {
                "no_bet_confidence_minimum": best_thresholds["no_bet_confidence_minimum"],
                "analysis_ready_confidence_minimum": best_thresholds["analysis_ready_confidence_minimum"],
            },
            "over_under": {
                "no_bet_confidence_minimum": best_thresholds["no_bet_confidence_minimum"],
                "data_quality_cap_value": best_thresholds["data_quality_cap_value"],
            },
            "halftime": {
                "missing_lineups_first_goal_cap": best_thresholds["missing_lineups_first_goal_cap"],
                "analysis_ready_confidence_minimum": best_thresholds["analysis_ready_confidence_minimum"],
            },
        }

        acc_before = _combined_accuracy(before)
        acc_after = _combined_accuracy(best_perf)

        return ThresholdTuningResult(
            recommended_thresholds=best_thresholds,
            market_thresholds=market_thresholds,
            performance_before=before,
            performance_after=best_perf,
            no_bet_rate_before=before.no_bet_rate,
            no_bet_rate_after=best_perf.no_bet_rate,
            accuracy_before=acc_before,
            accuracy_after=acc_after,
            candidates_evaluated=len(candidates),
            warnings=warnings,
        )


def _generate_threshold_candidates(base: dict[str, float]) -> list[dict[str, float]]:
    keys = list(ThresholdTuner.GRID.keys())
    value_lists = [ThresholdTuner.GRID[k] for k in keys]
    candidates: list[dict[str, float]] = []

    for combo in itertools.product(*value_lists):
        variant = dict(base)
        for key, value in zip(keys, combo):
            variant[key] = value
        candidates.append(variant)

    return candidates


def _threshold_objective(perf: MarketPerformance) -> float:
    accuracy = _combined_accuracy(perf)
    no_bet = perf.no_bet_rate or 0.0
    if no_bet > 0.95:
        return accuracy - 0.25
    if no_bet > 0.85:
        return accuracy - 0.10
    return accuracy + (1.0 - no_bet) * 0.05


def _combined_accuracy(perf: MarketPerformance) -> float:
    parts = [
        perf.one_x_two_accuracy or 0.0,
        perf.over_under_accuracy or 0.0,
        perf.halftime_bucket_accuracy or 0.0,
    ]
    return sum(parts) / len(parts)


def _sample_warnings(sample_size: int, candidates: int) -> list[str]:
    warnings: list[str] = []
    if sample_size < SMALL_SAMPLE_THRESHOLD:
        warnings.append(
            f"Sample size {sample_size} < {SMALL_SAMPLE_THRESHOLD}: threshold tuning is exploratory only."
        )
    if sample_size > 0 and candidates > sample_size * 2:
        warnings.append("Large threshold grid on small sample — treat recommendations as hypotheses.")
    return warnings
