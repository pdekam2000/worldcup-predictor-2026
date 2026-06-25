"""Leakage-safe historical backtest runner (Phase 51H)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.goal_timing.backtest.aggregator import aggregate_backtest_results, build_calibration_stats
from worldcup_predictor.goal_timing.config import BACKTEST_DEFAULT_LOOKBACK_DAYS, GOAL_TIMING_PREDICTION_LEAGUE_KEYS
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.outcome_adapter import build_evaluation_actuals

logger = logging.getLogger(__name__)


class GoalTimingBacktestRunner:
    """Run EGIE engine on finished historical fixtures — DB read only, no persist."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        lookback_days: int = BACKTEST_DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self.settings = settings or get_settings()
        self.lookback_days = lookback_days
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.engine = EliteGoalTimingEngine(
            feature_builder=GoalTimingFeatureBuilder(
                stored=self.stored,
                max_api_event_fetches=0,
            )
        )
        self.resolver = FixtureOutcomeResolver(self.settings)

    def default_window(self) -> tuple[datetime, datetime]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.lookback_days)
        return start, end

    def list_candidate_fixtures(
        self,
        *,
        competition_key: str,
        limit: int | None = None,
        before_kickoff: str | None = None,
    ) -> list[dict[str, Any]]:
        before = before_kickoff or datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows = self.stored.repo.list_finished_fixtures_before(
            before_kickoff=before,
            competition_keys=[competition_key],
            limit=limit,
        )
        return list(reversed(rows))

    def run(
        self,
        *,
        competition_key: str = "premier_league",
        limit: int | None = None,
        require_goal_events: bool = True,
    ) -> dict[str, Any]:
        start, end = self.default_window()
        results: list[dict[str, Any]] = []
        errors = 0

        with backtest_mode():
            fixtures = self.list_candidate_fixtures(
                competition_key=competition_key,
                limit=limit,
            )
            for row in fixtures:
                fixture_id = int(row["fixture_id"])
                home_team = str(row.get("home_team") or "")
                away_team = str(row.get("away_team") or "")
                kickoff = str(row.get("kickoff_utc") or "")
                try:
                    outcome = self.resolver.resolve(fixture_id)
                    if not outcome.is_finished:
                        continue

                    event_count = self.stored.repo.count_fixture_goal_events(fixture_id)
                    if require_goal_events and event_count == 0 and not row.get("first_goal_minute"):
                        continue

                    actuals = build_evaluation_actuals(
                        outcome,
                        home_team=home_team,
                        away_team=away_team,
                    )
                    evaluable = (
                        actuals["actual_first_goal_team"] is not None
                        or actuals["actual_first_goal_minute"] is not None
                        or str(actuals.get("final_score") or "").strip() in {"0-0", "0:0"}
                    )
                    if not evaluable:
                        continue

                    kickoff_dt = self.stored.parse_kickoff(kickoff)
                    features = self.engine.feature_builder.build(
                        fixture_id,
                        competition_key=competition_key,
                        as_of=kickoff_dt,
                        context={
                            "home_team": home_team,
                            "away_team": away_team,
                            "match_date": kickoff_dt,
                        },
                    )
                    prediction = self.engine.predict_from_features(
                        fixture_id,
                        features=features,
                        competition_key=competition_key,
                        context={
                            "home_team": home_team,
                            "away_team": away_team,
                            "match_date": kickoff_dt,
                        },
                    )
                    pred_dict = prediction.to_dict()

                    if prediction.no_prediction_flag:
                        results.append(
                            {
                                "fixture_id": fixture_id,
                                "competition_key": competition_key,
                                "home_team": home_team,
                                "away_team": away_team,
                                "kickoff_utc": kickoff,
                                "no_prediction_flag": True,
                                "data_quality_score": prediction.data_quality_score,
                                "confidence_score": prediction.confidence_score,
                                "evaluable": evaluable,
                                "reason": "dq_below_threshold_or_league",
                            }
                        )
                        continue

                    evaluation = evaluate_goal_timing_prediction(
                        fixture_id=fixture_id,
                        prediction_id=f"backtest-{fixture_id}",
                        predicted_first_goal_team=pred_dict.get("first_goal_team"),
                        predicted_first_goal_time_range=pred_dict.get("first_goal_time_range"),
                        estimated_first_goal_minute=pred_dict.get("display_estimated_first_goal_minute"),
                        actual_first_goal_team=actuals["actual_first_goal_team"],
                        actual_first_goal_minute=actuals["actual_first_goal_minute"],
                    )

                    results.append(
                        {
                            "fixture_id": fixture_id,
                            "competition_key": competition_key,
                            "home_team": home_team,
                            "away_team": away_team,
                            "kickoff_utc": kickoff,
                            "no_prediction_flag": False,
                            "data_quality_score": prediction.data_quality_score,
                            "confidence_score": prediction.confidence_score,
                            "predicted_first_goal_team": pred_dict.get("first_goal_team"),
                            "predicted_first_goal_time_range": pred_dict.get("first_goal_time_range"),
                            "predicted_minute": pred_dict.get("display_estimated_first_goal_minute"),
                            "actual_first_goal_team": actuals["actual_first_goal_team"],
                            "actual_first_goal_minute": actuals["actual_first_goal_minute"],
                            "final_score": actuals.get("final_score"),
                            "first_goal_team_status": evaluation.first_goal_team_status,
                            "time_range_status": evaluation.time_range_status,
                            "minute_tolerance_status": evaluation.minute_tolerance_status,
                            "evaluable": evaluable,
                            "goal_event_count": event_count,
                        }
                    )
                except Exception as exc:
                    logger.exception("Backtest failed fixture_id=%s", fixture_id)
                    errors += 1
                    results.append(
                        {
                            "fixture_id": fixture_id,
                            "competition_key": competition_key,
                            "error": str(exc),
                        }
                    )

        metrics = aggregate_backtest_results(results)
        calibration = build_calibration_stats(results)

        return {
            "status": "completed",
            "phase": "51H",
            "competition_key": competition_key,
            "competition_keys_available": list(GOAL_TIMING_PREDICTION_LEAGUE_KEYS),
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "lookback_days": self.lookback_days,
            "data_policy": "db_only_no_external_api_no_persist",
            "require_goal_events": require_goal_events,
            "errors": errors,
            "metrics": metrics,
            "calibration": calibration,
            "results": results,
        }
