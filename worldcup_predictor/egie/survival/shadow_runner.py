"""Run baseline EGIE and Survival EGIE in parallel (shadow mode)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from worldcup_predictor.egie.guards import backtest_mode
from worldcup_predictor.egie.survival.shadow_store import SurvivalShadowStore
from worldcup_predictor.egie.survival.survival_engine import SurvivalGoalTimingEngine
from worldcup_predictor.goal_timing.engine import EliteGoalTimingEngine
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction

logger = logging.getLogger(__name__)


class SurvivalShadowRunner:
    """Compare production engine vs survival layer without replacing production."""

    def __init__(
        self,
        *,
        baseline: EliteGoalTimingEngine | None = None,
        survival: SurvivalGoalTimingEngine | None = None,
        store: SurvivalShadowStore | None = None,
    ) -> None:
        self.baseline = baseline or EliteGoalTimingEngine()
        self.survival = survival or SurvivalGoalTimingEngine(
            stored=self.baseline.feature_builder.stored,
            feature_builder=self.baseline.feature_builder,
        )
        self.store = store or SurvivalShadowStore()

    def run_fixture(
        self,
        fixture_id: int,
        *,
        competition_key: str,
        as_of: datetime | None = None,
        context: dict[str, Any] | None = None,
        actuals: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        ctx = context or {}
        with backtest_mode():
            baseline_pred = self.baseline.predict_fixture(
                fixture_id,
                competition_key=competition_key,
                as_of=as_of,
                context=ctx,
            )
            survival_pred = self.survival.predict_fixture(
                fixture_id,
                competition_key=competition_key,
                as_of=as_of,
                context=ctx,
            )

        baseline_dict = baseline_pred.to_dict()
        record: dict[str, Any] = {
            "fixture_id": fixture_id,
            "competition_key": competition_key,
            "baseline": {
                "first_goal_team": baseline_dict.get("first_goal_team"),
                "first_goal_time_range": baseline_dict.get("first_goal_time_range"),
                "display_estimated_first_goal_minute": baseline_dict.get(
                    "display_estimated_first_goal_minute"
                ),
                "confidence_score": baseline_pred.confidence_score,
                "data_quality_score": baseline_pred.data_quality_score,
                "no_prediction_flag": baseline_pred.no_prediction_flag,
            },
            "survival": {
                "first_goal_team": survival_pred.get("first_goal_team"),
                "first_goal_time_range": survival_pred.get("first_goal_time_range"),
                "display_estimated_first_goal_minute": survival_pred.get(
                    "display_estimated_first_goal_minute"
                ),
                "range_probabilities": survival_pred.get("range_probabilities"),
                "team_probabilities": survival_pred.get("team_probabilities"),
                "confidence_score": survival_pred.get("confidence_score"),
                "data_quality_score": survival_pred.get("data_quality_score"),
                "no_prediction_flag": survival_pred.get("no_prediction_flag"),
                "model_version": survival_pred.get("model_version"),
            },
        }

        if actuals:
            act_team = actuals.get("actual_first_goal_team")
            act_minute = actuals.get("actual_first_goal_minute")
            if not baseline_pred.no_prediction_flag:
                base_eval = evaluate_goal_timing_prediction(
                    fixture_id=fixture_id,
                    prediction_id=f"shadow-baseline-{fixture_id}",
                    predicted_first_goal_team=baseline_dict.get("first_goal_team"),
                    predicted_first_goal_time_range=baseline_dict.get("first_goal_time_range"),
                    estimated_first_goal_minute=baseline_dict.get("display_estimated_first_goal_minute"),
                    actual_first_goal_team=act_team,
                    actual_first_goal_minute=act_minute,
                )
                record["baseline_eval"] = {
                    "first_goal_team_status": base_eval.first_goal_team_status,
                    "time_range_status": base_eval.time_range_status,
                    "minute_tolerance_status": base_eval.minute_tolerance_status,
                }
            if not survival_pred.get("no_prediction_flag"):
                surv_eval = evaluate_goal_timing_prediction(
                    fixture_id=fixture_id,
                    prediction_id=f"shadow-survival-{fixture_id}",
                    predicted_first_goal_team=survival_pred.get("first_goal_team"),
                    predicted_first_goal_time_range=survival_pred.get("first_goal_time_range"),
                    estimated_first_goal_minute=survival_pred.get("display_estimated_first_goal_minute"),
                    actual_first_goal_team=act_team,
                    actual_first_goal_minute=act_minute,
                )
                record["survival_eval"] = {
                    "first_goal_team_status": surv_eval.first_goal_team_status,
                    "time_range_status": surv_eval.time_range_status,
                    "minute_tolerance_status": surv_eval.minute_tolerance_status,
                }
            record["actuals"] = actuals

        if persist:
            self.store.append(record)
        return record
