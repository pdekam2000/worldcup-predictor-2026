"""Pre-match scan and prediction automation scheduler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.models import PredictionVersion
from worldcup_predictor.accuracy.service import record_match_prediction
from worldcup_predictor.agents.match_intelligence_builder import MatchIntelligenceBuilder
from worldcup_predictor.automation.models import (
    AutomationLogEntry,
    PreMatchAutomationResult,
    PreMatchWindowCounts,
)
from worldcup_predictor.automation.report_writer import PreMatchAutomationReportWriter
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.schedule.match_center import classify_status

logger = logging.getLogger(__name__)

DATA_QUALITY_REFRESH_THRESHOLD = 15.0


def version_for_window(window_hours: float) -> PredictionVersion:
    if window_hours <= 1.5:
        return "pre_6h"
    if window_hours <= 6:
        return "pre_6h"
    return "early_24h"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hours_until_kickoff(fixture: TournamentFixture, now: datetime) -> float:
    delta = fixture.kickoff_time - now
    return delta.total_seconds() / 3600.0


def _is_upcoming(fixture: TournamentFixture) -> bool:
    return classify_status(fixture.status) == "upcoming"


class PreMatchScheduler:
    """Scan upcoming fixtures and store versioned pre-match predictions."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        competition_key: str = "world_cup_2026",
        locale: str = "en",
        history_store: PredictionHistoryStore | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._competition_key = competition_key
        self._locale = locale
        self._store = history_store or PredictionHistoryStore()
        self._writer = PreMatchAutomationReportWriter()
        self._intel_builder = MatchIntelligenceBuilder(ApiFootballClient(self._settings))

    def run_window_scan(self, *, window_hours: float, selected_only: bool = False) -> PreMatchAutomationResult:
        target_version = version_for_window(window_hours)
        fixtures = self._load_upcoming_fixtures()
        if selected_only:
            fixtures = self._filter_selected_fixtures(fixtures)
        window_counts = self._count_windows(fixtures)
        candidates = [
            fixture
            for fixture in fixtures
            if _is_upcoming(fixture) and 0 <= _hours_until_kickoff(fixture, _utc_now()) <= window_hours
        ]
        result = PreMatchAutomationResult(
            scan_mode=f"window_{window_hours}h",
            window_hours=window_hours,
            lineup_final=False,
            matches_scanned=len(candidates),
            window_counts=window_counts,
        )
        for fixture in candidates:
            self._process_window_fixture(fixture, target_version, result)
        self._writer.write(result)
        return result

    def run_lineup_final_scan(self) -> PreMatchAutomationResult:
        fixtures = self._load_upcoming_fixtures()
        window_counts = self._count_windows(fixtures)
        now = _utc_now()
        candidates = [
            fixture
            for fixture in fixtures
            if _is_upcoming(fixture) and _hours_until_kickoff(fixture, now) >= 0
        ]
        result = PreMatchAutomationResult(
            scan_mode="lineup_final",
            window_hours=None,
            lineup_final=True,
            matches_scanned=len(candidates),
            window_counts=window_counts,
        )
        for fixture in candidates:
            self._process_lineup_final_fixture(fixture, result)
        self._writer.write(result)
        return result

    def count_upcoming_windows(self) -> PreMatchWindowCounts:
        return self._count_windows(self._load_upcoming_fixtures())

    def _load_upcoming_fixtures(self) -> list[TournamentFixture]:
        service = create_schedule_service(self._settings, competition_key=self._competition_key)
        fixtures = service.get_all_worldcup_fixtures()
        return sorted(fixtures, key=lambda item: item.kickoff_time)

    def _filter_selected_fixtures(self, fixtures: list[TournamentFixture]) -> list[TournamentFixture]:
        from worldcup_predictor.selection.match_selection_engine import MatchSelectionEngine

        engine = MatchSelectionEngine()
        shortlist = engine.build_shortlist(fixtures, competition_key=self._competition_key, days=3)
        auto_ids = {item.fixture_id for item in shortlist.auto_predict}
        return [fixture for fixture in fixtures if fixture.fixture_id in auto_ids]

    @staticmethod
    def _count_windows(fixtures: list[TournamentFixture]) -> PreMatchWindowCounts:
        now = _utc_now()
        counts = PreMatchWindowCounts()
        for fixture in fixtures:
            if not _is_upcoming(fixture):
                continue
            hours = _hours_until_kickoff(fixture, now)
            if hours < 0:
                continue
            if hours <= 24:
                counts.within_24h += 1
            if hours <= 6:
                counts.within_6h += 1
            if hours <= 1.5:
                counts.within_90m += 1
        return counts

    def _lineups_available(self, fixture_id: int) -> bool:
        try:
            report = self._intel_builder.build_by_fixture_id(fixture_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lineup probe failed for fixture %s: %s", fixture_id, exc)
            return False
        return bool(report.lineups and report.lineups.get("available"))

    def _process_window_fixture(
        self,
        fixture: TournamentFixture,
        target_version: PredictionVersion,
        result: PreMatchAutomationResult,
    ) -> None:
        match_name = f"{fixture.home_team} vs {fixture.away_team}"
        existing_version = self._store.latest_with_version(fixture.fixture_id, target_version)
        latest_any = self._store.latest_for_fixture(fixture.fixture_id)
        lineups_ok = self._lineups_available(fixture.fixture_id)

        if existing_version is None and latest_any is None:
            prediction = self._run_pipeline(fixture.fixture_id)
            if prediction is None:
                result.errors += 1
                result.log.append(
                    AutomationLogEntry(
                        fixture_id=fixture.fixture_id,
                        match_name=match_name,
                        action="error",
                        prediction_version=target_version,
                        message="PredictPipeline failed",
                    )
                )
                return
            self._store_prediction(
                fixture,
                prediction,
                target_version,
                result,
                reason=None,
                refreshed_from=None,
                lineups_ok=lineups_ok,
            )
            return

        if existing_version is not None:
            prediction = self._run_pipeline(fixture.fixture_id)
            if prediction is None:
                result.errors += 1
                result.log.append(
                    AutomationLogEntry(
                        fixture_id=fixture.fixture_id,
                        match_name=match_name,
                        action="error",
                        prediction_version=target_version,
                        message="PredictPipeline failed during refresh check",
                    )
                )
                return
            new_dq = prediction.confidence_breakdown.data_quality_score if prediction.confidence_breakdown else 0.0
            old_dq = existing_version.data_quality_score
            if new_dq - old_dq >= DATA_QUALITY_REFRESH_THRESHOLD:
                self._store_prediction(
                    fixture,
                    prediction,
                    target_version,
                    result,
                    reason=f"Data quality improved by {new_dq - old_dq:.1f} points",
                    refreshed_from=existing_version.prediction_id,
                    lineups_ok=lineups_ok,
                    action="refreshed",
                )
                return

            if lineups_ok and not existing_version.lineups_available and not self._store.has_version(
                fixture.fixture_id, "final_lineup"
            ):
                self._store_prediction(
                    fixture,
                    prediction,
                    "final_lineup",
                    result,
                    reason="Official lineups became available",
                    refreshed_from=existing_version.prediction_id,
                    lineups_ok=True,
                )
                return

            self._log_skip(
                result,
                fixture,
                target_version,
                f"Version `{target_version}` already stored — no refresh threshold met",
            )
            return

        prediction = self._run_pipeline(fixture.fixture_id)
        if prediction is None:
            result.errors += 1
            result.log.append(
                AutomationLogEntry(
                    fixture_id=fixture.fixture_id,
                    match_name=match_name,
                    action="error",
                    prediction_version=target_version,
                    message="PredictPipeline failed",
                )
            )
            return
        self._store_prediction(
            fixture,
            prediction,
            target_version,
            result,
            reason=None,
            refreshed_from=latest_any.prediction_id if latest_any else None,
            lineups_ok=lineups_ok,
        )

    def _process_lineup_final_fixture(
        self,
        fixture: TournamentFixture,
        result: PreMatchAutomationResult,
    ) -> None:
        if self._store.has_version(fixture.fixture_id, "final_lineup"):
            self._log_skip(
                result,
                fixture,
                "final_lineup",
                "Final lineup version already stored",
            )
            return

        if not self._lineups_available(fixture.fixture_id):
            self._log_skip(
                result,
                fixture,
                "final_lineup",
                "Official lineups not available — preliminary only",
            )
            return

        latest_any = self._store.latest_for_fixture(fixture.fixture_id)
        prediction = self._run_pipeline(fixture.fixture_id)
        if prediction is None:
            result.errors += 1
            result.log.append(
                AutomationLogEntry(
                    fixture_id=fixture.fixture_id,
                    match_name=f"{fixture.home_team} vs {fixture.away_team}",
                    action="error",
                    prediction_version="final_lineup",
                    message="PredictPipeline failed",
                )
            )
            return
        self._store_prediction(
            fixture,
            prediction,
            "final_lineup",
            result,
            reason="Official lineups published — final pre-match version",
            refreshed_from=latest_any.prediction_id if latest_any else None,
            lineups_ok=True,
        )

    def _run_pipeline(self, fixture_id: int) -> MatchPrediction | None:
        pipeline = PredictPipeline(
            self._settings,
            locale=self._locale,
            competition_key=self._competition_key,
        )
        outcome = pipeline.run(fixture_id, record_history=False)
        if not outcome.success:
            return None
        return outcome.prediction

    def _store_prediction(
        self,
        fixture: TournamentFixture,
        prediction: MatchPrediction,
        version: PredictionVersion,
        result: PreMatchAutomationResult,
        *,
        reason: str | None,
        refreshed_from: str | None,
        lineups_ok: bool,
        action: str = "created",
    ) -> None:
        match_name = f"{fixture.home_team} vs {fixture.away_team}"
        try:
            record = record_match_prediction(
                prediction,
                self._store,
                prediction_version=version,
                refreshed_from_prediction_id=refreshed_from,
                reason_for_refresh=reason,
                lineups_available=lineups_ok,
            )
            preliminary_note = " (preliminary — lineups missing)" if record.is_preliminary else ""
            version_label = f"`{version}`{preliminary_note}"
            if action == "refreshed":
                result.predictions_refreshed += 1
            else:
                result.predictions_created += 1
            result.log.append(
                AutomationLogEntry(
                    fixture_id=fixture.fixture_id,
                    match_name=match_name,
                    action=action,  # type: ignore[arg-type]
                    prediction_version=version,
                    message=f"Stored {version_label}. no_bet={prediction.no_bet_flag}. {reason or ''}".strip(),
                    prediction_id=record.prediction_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Automation failed for fixture %s", fixture.fixture_id)
            result.errors += 1
            result.log.append(
                AutomationLogEntry(
                    fixture_id=fixture.fixture_id,
                    match_name=match_name,
                    action="error",
                    prediction_version=version,
                    message=str(exc),
                )
            )

    def _log_skip(
        self,
        result: PreMatchAutomationResult,
        fixture: TournamentFixture,
        version: str,
        message: str,
    ) -> None:
        result.predictions_skipped += 1
        result.log.append(
            AutomationLogEntry(
                fixture_id=fixture.fixture_id,
                match_name=f"{fixture.home_team} vs {fixture.away_team}",
                action="skipped",
                prediction_version=version,
                message=message,
            )
        )
