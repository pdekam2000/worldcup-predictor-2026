from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from pathlib import Path

from worldcup_predictor.agents.base import AgentContext
from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
from worldcup_predictor.backtesting.historical_loader import (
    HistoricalLoader,
    HistoricalMatchRow,
    build_form_history,
    build_intelligence_report,
)
from worldcup_predictor.backtesting.metrics import compute_metrics
from worldcup_predictor.backtesting.models import MatchBacktestResult
from worldcup_predictor.calibration.models import MarketPerformance
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.prediction.scoring_engine import ScoringEngine


@dataclass
class _CachedMatch:
    row: HistoricalMatchRow
    baseline: MatchPrediction
    report: object
    specialist: MatchSpecialistReport | None


class CalibrationEvaluator:
    """Cache intelligence + baseline once; re-run decision engine for tuning."""

    def __init__(
        self,
        csv_path: Path | str,
        settings: Settings | None = None,
        *,
        run_specialists: bool = True,
        locale: str = "en",
    ) -> None:
        self._settings = settings or get_settings()
        self._locale = locale
        self._scoring = ScoringEngine()
        self._cached: list[_CachedMatch] = []
        self._is_demo = False
        self._prepare(csv_path, run_specialists)

    @property
    def sample_size(self) -> int:
        return len(self._cached)

    @property
    def is_demo_data(self) -> bool:
        return self._is_demo

    def evaluate(
        self,
        factor_weights: dict[str, float],
        thresholds: dict[str, float] | None = None,
    ) -> tuple[list[MatchBacktestResult], MarketPerformance]:
        engine = WeightedDecisionEngine(factor_weights=factor_weights, thresholds=thresholds)
        results: list[MatchBacktestResult] = []

        for item in self._cached:
            baseline = copy.deepcopy(item.baseline)
            decision = engine.decide(
                DecisionInput(
                    baseline=baseline,
                    report=item.report,  # type: ignore[arg-type]
                    specialist_report=item.specialist,
                )
            )
            prediction = engine.apply_decision(baseline, decision)

            predicted_ht = HistoricalMatchRow.halftime_bucket(prediction.halftime.estimated_total_goals)
            ht_evaluated = item.row.halftime_total_goals is not None
            ht_correct: bool | None = None
            actual_ht: str | None = None
            if ht_evaluated:
                actual_ht = HistoricalMatchRow.halftime_bucket(item.row.halftime_total_goals)  # type: ignore[arg-type]
                ht_correct = predicted_ht == actual_ht

            results.append(
                MatchBacktestResult(
                    fixture_id=item.row.fixture_id,
                    match_name=prediction.match_name,
                    date=item.row.date.strftime("%Y-%m-%d"),
                    competition=item.row.competition,
                    predicted_1x2=prediction.one_x_two.selection,
                    actual_1x2=item.row.actual_1x2,
                    one_x_two_correct=prediction.one_x_two.selection == item.row.actual_1x2,
                    predicted_over_under=prediction.over_under.selection,
                    actual_over_under=item.row.actual_over_under,
                    over_under_correct=prediction.over_under.selection == item.row.actual_over_under,
                    predicted_halftime_bucket=predicted_ht,
                    actual_halftime_bucket=actual_ht,
                    halftime_bucket_correct=ht_correct,
                    halftime_evaluated=ht_evaluated,
                    confidence_score=prediction.confidence_score,
                    no_bet_flag=prediction.no_bet_flag,
                    first_goal_skipped=True,
                    specialists_ran=item.specialist is not None,
                )
            )

        metrics = compute_metrics(results, is_demo_data=self._is_demo)
        perf = MarketPerformance(
            one_x_two_accuracy=metrics.one_x_two_accuracy,
            over_under_accuracy=metrics.over_under_2_5_accuracy,
            halftime_bucket_accuracy=metrics.halftime_bucket_accuracy,
            average_confidence=metrics.average_confidence,
            no_bet_rate=metrics.no_bet_rate,
            sample_size=metrics.total_matches,
        )
        return results, perf

    def _prepare(self, csv_path: Path | str, run_specialists: bool) -> None:
        path = Path(csv_path)
        loader = HistoricalLoader(path)
        rows = loader.load(create_sample_if_missing=True)
        self._is_demo = any(r.is_demo for r in rows) or _file_is_demo(path)
        form_history = build_form_history(rows)

        for row in rows:
            home_form, away_form = form_history.get(row.fixture_id, ([], []))
            report = build_intelligence_report(row, home_form=home_form, away_form=away_form)
            context = AgentContext(
                settings=self._settings,
                competition_key=report.fixture.competition_key if report.fixture else "world_cup_2026",
                locale=self._locale,
            )
            context.shared["intelligence_reports"] = {row.fixture_id: report}

            specialist: MatchSpecialistReport | None = None
            if run_specialists:
                orchestrator = SpecialistOrchestrator(context)
                result = orchestrator.run(fixture_id=row.fixture_id)
                if result.success and isinstance(result.data, MatchSpecialistReport):
                    specialist = result.data
                    report.specialist_report = specialist

            baseline = self._scoring.predict(
                report,
                specialist_report=specialist,
                use_weighted_decision=False,
            )
            self._cached.append(_CachedMatch(row=row, baseline=baseline, report=report, specialist=specialist))


def market_score(perf: MarketPerformance, market: str) -> float:
    if market == "1x2":
        return perf.one_x_two_accuracy or 0.0
    if market == "over_under":
        return perf.over_under_accuracy or 0.0
    if market == "halftime":
        return perf.halftime_bucket_accuracy or 0.0
    values = [
        perf.one_x_two_accuracy or 0.0,
        perf.over_under_accuracy or 0.0,
        perf.halftime_bucket_accuracy or 0.0,
    ]
    return sum(values) / len(values)


def overall_score(perf: MarketPerformance) -> float:
    parts = [
        perf.one_x_two_accuracy or 0.0,
        perf.over_under_accuracy or 0.0,
        perf.halftime_bucket_accuracy or 0.0,
    ]
    base = sum(parts) / len(parts)
    penalty = (perf.no_bet_rate or 0.0) * 0.15
    return base - penalty


def _file_is_demo(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return "DEMO DATA" in path.read_text(encoding="utf-8")[:200]
    except OSError:
        return False


def generate_weight_candidates(
    base: dict[str, float],
    *,
    random_samples: int = 12,
    seed: int = 42,
) -> list[dict[str, float]]:
    from worldcup_predictor.config.model_weights import normalize_weights

    rng = random.Random(seed)
    candidates: list[dict[str, float]] = [normalize_weights(dict(base))]
    keys = list(base.keys())

    for key in keys:
        for mult in (0.85, 0.9, 1.1, 1.15):
            variant = dict(base)
            variant[key] = variant[key] * mult
            candidates.append(normalize_weights(variant))

    for _ in range(random_samples):
        variant = {key: base[key] * rng.uniform(0.78, 1.22) for key in keys}
        candidates.append(normalize_weights(variant))

    unique: list[dict[str, float]] = []
    seen: set[tuple] = set()
    for candidate in candidates:
        key = tuple(sorted((k, round(v, 4)) for k, v in candidate.items()))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique
