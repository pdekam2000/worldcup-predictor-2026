from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.accuracy.evaluator import evaluate_all
from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.metrics import compute_accuracy_metrics
from worldcup_predictor.accuracy.models import (
    AccuracySummaryMetrics,
    EvaluatedPrediction,
    PredictionHistoryRecord,
    PredictionVersion,
)
from worldcup_predictor.accuracy.report_writer import AccuracyReportWriter
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.results.match_results_store import save_finished_fixtures
from worldcup_predictor.schedule.match_center import build_match_center, classify_status


def _split_match_name(match_name: str) -> tuple[str, str]:
    if " vs " in match_name:
        home, away = match_name.split(" vs ", 1)
        return home.strip(), away.strip()
    return match_name, "Unknown"


def _prediction_source(prediction: MatchPrediction) -> str:
    if prediction.is_placeholder:
        return "demo"
    meta_source = prediction.metadata.get("source")
    if meta_source:
        return str(meta_source)
    return "live"


def _scoreline_label(prediction: MatchPrediction) -> str | None:
    scoreline = prediction.scoreline
    if scoreline is None:
        return None
    return scoreline.label


def record_from_match_prediction(
    prediction: MatchPrediction,
    *,
    prediction_version: PredictionVersion = "manual",
    refreshed_from_prediction_id: str | None = None,
    reason_for_refresh: str | None = None,
    lineups_available: bool | None = None,
    prediction_id: str | None = None,
) -> PredictionHistoryRecord:
    home, away = _split_match_name(prediction.match_name)
    kickoff = prediction.kickoff_utc
    date_str = kickoff.strftime("%Y-%m-%d") if kickoff else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dq = prediction.confidence_breakdown.data_quality_score if prediction.confidence_breakdown else 0.0
    lineups_ok = lineups_available if lineups_available is not None else prediction.lineup_warning is None
    created_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    extended_json: str | None = None
    try:
        from worldcup_predictor.prediction.extended_markets import (
            build_extended_markets,
            load_extended_markets_from_prediction,
        )

        snap = load_extended_markets_from_prediction(prediction) or build_extended_markets(prediction, None)
        extended_json = json.dumps(snap.to_dict(), ensure_ascii=False)
        prediction.metadata = dict(prediction.metadata or {})
        prediction.metadata["extended_markets"] = extended_json
    except Exception:
        extended_json = (prediction.metadata or {}).get("extended_markets")
        if extended_json and not isinstance(extended_json, str):
            extended_json = json.dumps(extended_json, ensure_ascii=False)
    return PredictionHistoryRecord(
        fixture_id=prediction.fixture_id,
        date=date_str,
        home_team=home,
        away_team=away,
        predicted_1x2=prediction.one_x_two.selection,
        predicted_over_under_2_5=prediction.over_under.selection,
        predicted_halftime_goals=prediction.halftime.estimated_total_goals,
        predicted_first_goal_team=prediction.first_goal.team,
        predicted_scoreline=_scoreline_label(prediction),
        predicted_first_goal_scorer=prediction.first_goal.player,
        confidence_score=prediction.confidence_score,
        risk_level=prediction.risk_level,
        no_bet_flag=prediction.no_bet_flag,
        data_quality_score=dq,
        source=_prediction_source(prediction),
        created_at=created_at,
        prediction_id=prediction_id or uuid.uuid4().hex,
        prediction_version=prediction_version,
        refreshed_from_prediction_id=refreshed_from_prediction_id,
        reason_for_refresh=reason_for_refresh,
        lineups_available=lineups_ok,
        is_preliminary=not lineups_ok,
        extended_markets_json=extended_json,
    )


def record_match_prediction(
    prediction: MatchPrediction,
    store: PredictionHistoryStore | None = None,
    **kwargs: object,
) -> PredictionHistoryRecord:
    """Persist a pre-match prediction run to learning memory."""
    target = store or PredictionHistoryStore()
    record = record_from_match_prediction(prediction, **kwargs)  # type: ignore[arg-type]
    target.append(record)
    return record


@dataclass
class AccuracyTrackerSnapshot:
    metrics: AccuracySummaryMetrics
    evaluated: list[EvaluatedPrediction]
    recent_predictions: list[PredictionHistoryRecord]
    pending_predictions: int


class AccuracyTrackerService:
    """Evaluate stored predictions against finished fixtures and write reports."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        competition_key: str = "world_cup_2026",
        history_path: Path | str | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._competition_key = competition_key
        self._store = PredictionHistoryStore(history_path or PredictionHistoryStore().path)
        self._writer = AccuracyReportWriter()

    def refresh(
        self,
        fixtures: list[TournamentFixture] | None = None,
    ) -> AccuracyTrackerSnapshot:
        latest = self._store.latest_by_fixture()
        if fixtures is None:
            schedule = create_schedule_service(self._settings, competition_key=self._competition_key)
            center = build_match_center(schedule, self._settings, enrich_live=False, enrich_finished_limit=50)
            fixtures = center.finished + center.live + center.upcoming

        save_finished_fixtures([f for f in fixtures if classify_status(f.status) == "finished"])

        evaluated = evaluate_all(latest, fixtures)
        finished_ids = {item.fixture_id for item in evaluated}
        pending = sum(1 for fixture_id in latest if fixture_id not in finished_ids)
        total_predictions = len(latest)
        self._writer.write(evaluated, pending_predictions=pending)
        metrics = compute_accuracy_metrics(
            evaluated,
            pending_predictions=pending,
            total_predictions=total_predictions,
        )
        return AccuracyTrackerSnapshot(
            metrics=metrics,
            evaluated=evaluated,
            recent_predictions=self._store.recent(25),
            pending_predictions=pending,
        )

    def load_summary_from_disk(self) -> AccuracyTrackerSnapshot | None:
        json_path = Path("reports/accuracy/accuracy_summary.json")
        if not json_path.exists():
            return None
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        metrics_dict = payload.get("metrics", {})
        evaluated_raw = payload.get("evaluated_predictions", [])
        evaluated = [EvaluatedPrediction.from_dict(item) for item in evaluated_raw]
        metrics = AccuracySummaryMetrics(
            total_evaluated=int(metrics_dict.get("total_evaluated", 0)),
            one_x_two_accuracy=metrics_dict.get("one_x_two_accuracy"),
            over_under_2_5_accuracy=metrics_dict.get("over_under_2_5_accuracy"),
            halftime_bucket_accuracy=metrics_dict.get("halftime_bucket_accuracy"),
            halftime_evaluated_count=int(metrics_dict.get("halftime_evaluated_count", 0)),
            scoreline_exact_accuracy=metrics_dict.get("scoreline_exact_accuracy"),
            scoreline_evaluated_count=int(metrics_dict.get("scoreline_evaluated_count", 0)),
            first_goal_accuracy=metrics_dict.get("first_goal_accuracy"),
            first_goal_evaluated_count=int(metrics_dict.get("first_goal_evaluated_count", 0)),
            total_predictions=int(metrics_dict.get("total_predictions", 0)),
            model_grade=str(metrics_dict.get("model_grade", "—")),
            best_market=metrics_dict.get("best_market"),
            worst_market=metrics_dict.get("worst_market"),
            average_confidence=float(metrics_dict.get("average_confidence", 0.0)),
            no_bet_count=int(metrics_dict.get("no_bet_count", 0)),
            no_bet_one_x_two_accuracy=metrics_dict.get("no_bet_one_x_two_accuracy"),
            non_no_bet_one_x_two_accuracy=metrics_dict.get("non_no_bet_one_x_two_accuracy"),
            no_bet_over_under_accuracy=metrics_dict.get("no_bet_over_under_accuracy"),
            non_no_bet_over_under_accuracy=metrics_dict.get("non_no_bet_over_under_accuracy"),
            best_confidence_range=metrics_dict.get("best_confidence_range"),
            worst_confidence_range=metrics_dict.get("worst_confidence_range"),
            pending_predictions=int(metrics_dict.get("pending_predictions", 0)),
            first_goal_skipped_count=int(metrics_dict.get("first_goal_skipped_count", 0)),
            data_limitations=list(metrics_dict.get("data_limitations", [])),
        )
        return AccuracyTrackerSnapshot(
            metrics=metrics,
            evaluated=evaluated,
            recent_predictions=self._store.recent(25),
            pending_predictions=metrics.pending_predictions,
        )

    def get_stored_record(self, fixture_id: int) -> PredictionHistoryRecord | None:
        return self._store.latest_by_fixture().get(fixture_id)

    def get_evaluation_for_fixture(
        self,
        fixture: TournamentFixture,
        fixtures: list[TournamentFixture] | None = None,
    ) -> EvaluatedPrediction | None:
        record = self.get_stored_record(fixture.fixture_id)
        if record is None:
            return None
        if fixtures is None:
            fixtures = [fixture]
        results = evaluate_all({fixture.fixture_id: record}, fixtures)
        return results[0] if results else None
