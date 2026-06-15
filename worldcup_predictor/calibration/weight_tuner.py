from __future__ import annotations

from pathlib import Path

from worldcup_predictor.calibration.evaluator import (
    CalibrationEvaluator,
    generate_weight_candidates,
    market_score,
    overall_score,
)
from worldcup_predictor.calibration.models import MarketPerformance, WeightTuningResult
from worldcup_predictor.config.model_weights import (
    MARKET_FACTOR_PRIORITIES,
    get_factor_weights,
    normalize_weights,
)
from worldcup_predictor.config.settings import Settings, get_settings

SMALL_SAMPLE_THRESHOLD = 100


class WeightTuner:
    """Grid/random search over factor weights using cached backtest evaluation."""

    def __init__(self, settings: Settings | None = None, *, locale: str = "en") -> None:
        self._settings = settings or get_settings()
        self._locale = locale

    def tune(
        self,
        csv_path: Path | str,
        evaluator: CalibrationEvaluator | None = None,
    ) -> WeightTuningResult:
        active_evaluator = evaluator or CalibrationEvaluator(
            csv_path, self._settings, locale=self._locale
        )
        base_weights = get_factor_weights(use_calibrated=False)
        default_thresholds = None  # use engine defaults during weight search

        _, before = active_evaluator.evaluate(base_weights, default_thresholds)
        candidates = generate_weight_candidates(base_weights)
        warnings = _sample_warnings(active_evaluator.sample_size, len(candidates))

        best_overall = base_weights
        best_1x2 = base_weights
        best_ou = base_weights
        best_ht = base_weights
        best_overall_score = overall_score(before)
        best_1x2_score = market_score(before, "1x2")
        best_ou_score = market_score(before, "over_under")
        best_ht_score = market_score(before, "halftime")

        for candidate in candidates:
            _, perf = active_evaluator.evaluate(candidate, default_thresholds)
            score = overall_score(perf)
            if score > best_overall_score:
                best_overall_score = score
                best_overall = candidate
            s1 = market_score(perf, "1x2")
            if s1 > best_1x2_score:
                best_1x2_score = s1
                best_1x2 = candidate
            sou = market_score(perf, "over_under")
            if sou > best_ou_score:
                best_ou_score = sou
                best_ou = candidate
            sht = market_score(perf, "halftime")
            if sht > best_ht_score:
                best_ht_score = sht
                best_ht = candidate

        _, after = active_evaluator.evaluate(best_overall, default_thresholds)

        return WeightTuningResult(
            best_weights_overall=normalize_weights(best_overall),
            best_weights_1x2=normalize_weights(best_1x2),
            best_weights_over_under=normalize_weights(best_ou),
            best_weights_halftime=normalize_weights(best_ht),
            performance_before=before,
            performance_after=after,
            candidates_evaluated=len(candidates),
            warnings=warnings,
        )


def _sample_warnings(sample_size: int, candidates: int) -> list[str]:
    warnings: list[str] = []
    if sample_size < SMALL_SAMPLE_THRESHOLD:
        warnings.append(
            f"Sample size {sample_size} < {SMALL_SAMPLE_THRESHOLD}: weight search is exploratory "
            "and prone to overfitting."
        )
    if sample_size > 0 and candidates > sample_size * 3:
        warnings.append(
            f"Evaluated {candidates} weight sets on {sample_size} matches — high overfitting risk."
        )
    return warnings


def market_weight_hint(market: str) -> list[str]:
    return MARKET_FACTOR_PRIORITIES.get(market, [])
