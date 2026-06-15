from __future__ import annotations

import logging
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
from worldcup_predictor.backtesting.models import BacktestRunResult, MatchBacktestResult
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.prediction.scoring_engine import ScoringEngine

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Run historical backtests through scoring + weighted decision pipeline."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        run_specialists: bool = True,
        locale: str = "en",
        factor_weights: dict[str, float] | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._run_specialists = run_specialists
        self._locale = locale
        self._factor_weights = factor_weights
        self._thresholds = thresholds
        self._engine = ScoringEngine()

    def run(self, csv_path: Path | str) -> BacktestRunResult:
        loader = HistoricalLoader(csv_path)
        rows = loader.load(create_sample_if_missing=True)
        is_demo = any(row.is_demo for row in rows) or _file_is_demo(Path(csv_path))

        form_history = build_form_history(rows)
        match_results: list[MatchBacktestResult] = []

        for row in rows:
            try:
                match_results.append(self._evaluate_match(row, form_history))
            except Exception as exc:  # noqa: BLE001 — collect per-match failures
                logger.exception("Backtest failed for fixture %s", row.fixture_id)
                match_results.append(
                    MatchBacktestResult(
                        fixture_id=row.fixture_id,
                        match_name=f"{row.home_team} vs {row.away_team}",
                        date=row.date.strftime("%Y-%m-%d"),
                        competition=row.competition,
                        predicted_1x2="unknown",
                        actual_1x2=row.actual_1x2,
                        one_x_two_correct=False,
                        predicted_over_under="unknown",
                        actual_over_under=row.actual_over_under,
                        over_under_correct=False,
                        predicted_halftime_bucket=None,
                        actual_halftime_bucket=None,
                        halftime_bucket_correct=None,
                        halftime_evaluated=False,
                        confidence_score=0.0,
                        no_bet_flag=True,
                        errors=[str(exc)],
                    )
                )

        metrics = compute_metrics(match_results, is_demo_data=is_demo)
        source = "demo_csv" if is_demo else "csv"
        return BacktestRunResult(
            match_results=match_results,
            metrics=metrics,
            csv_path=str(csv_path),
            is_demo_data=is_demo,
            source_label=source,
        )

    def _evaluate_match(
        self,
        row: HistoricalMatchRow,
        form_history: dict[int, tuple[list[str], list[str]]],
    ) -> MatchBacktestResult:
        home_form, away_form = form_history.get(row.fixture_id, ([], []))
        report = build_intelligence_report(row, home_form=home_form, away_form=away_form)

        context = AgentContext(
            settings=self._settings,
            competition_key=report.fixture.competition_key if report.fixture else "world_cup_2026",
            locale=self._locale,
        )
        context.shared["intelligence_reports"] = {row.fixture_id: report}

        specialist_report: MatchSpecialistReport | None = None
        specialists_ran = False
        if self._run_specialists:
            orchestrator = SpecialistOrchestrator(context)
            specialist_result = orchestrator.run(fixture_id=row.fixture_id)
            if specialist_result.success and isinstance(specialist_result.data, MatchSpecialistReport):
                specialist_report = specialist_result.data
                report.specialist_report = specialist_report
                specialists_ran = True

        prediction = self._engine.predict(
            report,
            specialist_report=specialist_report,
            use_weighted_decision=True,
            factor_weights=self._factor_weights,
            thresholds=self._thresholds,
        )

        predicted_ht_bucket = HistoricalMatchRow.halftime_bucket(prediction.halftime.estimated_total_goals)
        actual_ht_bucket: str | None = None
        ht_correct: bool | None = None
        ht_evaluated = row.halftime_total_goals is not None
        if ht_evaluated:
            actual_ht_bucket = HistoricalMatchRow.halftime_bucket(row.halftime_total_goals)  # type: ignore[arg-type]
            ht_correct = predicted_ht_bucket == actual_ht_bucket

        return MatchBacktestResult(
            fixture_id=row.fixture_id,
            match_name=prediction.match_name,
            date=row.date.strftime("%Y-%m-%d"),
            competition=row.competition,
            predicted_1x2=prediction.one_x_two.selection,
            actual_1x2=row.actual_1x2,
            one_x_two_correct=prediction.one_x_two.selection == row.actual_1x2,
            predicted_over_under=prediction.over_under.selection,
            actual_over_under=row.actual_over_under,
            over_under_correct=prediction.over_under.selection == row.actual_over_under,
            predicted_halftime_bucket=predicted_ht_bucket,
            actual_halftime_bucket=actual_ht_bucket,
            halftime_bucket_correct=ht_correct,
            halftime_evaluated=ht_evaluated,
            confidence_score=prediction.confidence_score,
            no_bet_flag=prediction.no_bet_flag,
            first_goal_skipped=True,
            specialists_ran=specialists_ran,
        )


def _file_is_demo(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        head = path.read_text(encoding="utf-8")[:200]
    except OSError:
        return False
    return "DEMO DATA" in head
