"""Elite Goal Timing Intelligence Engine — orchestrator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.goal_timing.agents.orchestrator import GoalTimingAgentOrchestrator
from worldcup_predictor.goal_timing.calibration import GoalTimingCalibrator
from worldcup_predictor.goal_timing.confidence import GoalTimingConfidenceEngine
from worldcup_predictor.goal_timing.config import (
    GOAL_TIMING_MINUTE_RANGES,
    GOAL_TIMING_MODEL_VERSION,
    GOAL_TIMING_PREDICTION_LEAGUE_KEYS,
    MIN_DATA_QUALITY_FOR_PREDICTION,
)
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.explanation import GoalTimingExplanationGenerator
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.leagues import is_goal_timing_prediction_league
from worldcup_predictor.goal_timing.models import GoalTimingPredictionResult
from worldcup_predictor.goal_timing.models_stat.baseline import GoalTimingBaselineModel


class EliteGoalTimingEngine:
    """Independent goal-timing prediction pipeline (not legacy 1X2)."""

    def __init__(
        self,
        *,
        feature_builder: GoalTimingFeatureBuilder | None = None,
        stored: StoredGoalTimingAdapter | None = None,
    ) -> None:
        stored = stored or StoredGoalTimingAdapter()
        self.feature_builder = feature_builder or GoalTimingFeatureBuilder(
            stored=stored,
            max_api_event_fetches=0,
        )
        self.agent_orchestrator = GoalTimingAgentOrchestrator()
        self.baseline_model = GoalTimingBaselineModel()
        self.calibrator = GoalTimingCalibrator()
        self.confidence_engine = GoalTimingConfidenceEngine()
        self.explanation_generator = GoalTimingExplanationGenerator()

    def predict_fixture(
        self,
        fixture_id: int,
        *,
        competition_key: str | None = None,
        as_of: datetime | None = None,
        context: dict[str, Any] | None = None,
    ) -> GoalTimingPredictionResult:
        ctx = context or {}
        comp_key = competition_key
        if not comp_key:
            target = self.feature_builder.stored.get_target_fixture(fixture_id)
            comp_key = str((target or {}).get("competition_key") or "premier_league")

        features = self.feature_builder.build(
            fixture_id,
            competition_key=comp_key,
            as_of=as_of,
            context=ctx,
        )
        return self.predict_from_features(
            fixture_id,
            features=features,
            competition_key=comp_key,
            context=ctx,
        )

    def predict_from_features(
        self,
        fixture_id: int,
        *,
        features: dict[str, Any],
        competition_key: str,
        context: dict[str, Any] | None = None,
    ) -> GoalTimingPredictionResult:
        ctx = context or {}
        agent_outputs = self.agent_orchestrator.run(
            fixture_id,
            features=features,
            context=ctx,
        )
        raw = self.baseline_model.predict(features, agent_outputs)
        calibrated = self.calibrator.calibrate(raw)
        confidence, data_quality, model_confidence = self.confidence_engine.score(
            features, agent_outputs, calibrated
        )

        league_ok = is_goal_timing_prediction_league(competition_key)
        no_prediction = (not league_ok) or data_quality < MIN_DATA_QUALITY_FOR_PREDICTION

        home_team = str(ctx.get("home_team") or features.get("home_team") or "Home")
        away_team = str(ctx.get("away_team") or features.get("away_team") or "Away")
        match_date = ctx.get("match_date")
        if match_date and isinstance(match_date, str):
            try:
                match_date = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
            except ValueError:
                match_date = None

        explanation = self.explanation_generator.generate(
            calibrated,
            agent_outputs,
            data_quality=data_quality,
            no_prediction=no_prediction,
            home_team=home_team,
            away_team=away_team,
        )

        agent_breakdown = {
            k: v.to_dict() if hasattr(v, "to_dict") else v
            for k, v in agent_outputs.items()
        }
        agent_breakdown["match_first_goal_range_probs"] = raw.get("match_first_goal_range_probs", {})
        agent_breakdown["audit_details"] = {
            "weighted_average_minute": raw.get("weighted_average_minute"),
            "model_confidence_score": model_confidence,
            "bucket_representative_minute": raw.get("bucket_representative_minute"),
        }

        return GoalTimingPredictionResult(
            fixture_id=fixture_id,
            competition_key=competition_key,
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            first_goal_team=calibrated.get("first_goal_team", "none"),
            first_goal_time_range=calibrated.get("first_goal_time_range", GOAL_TIMING_MINUTE_RANGES[0]),
            display_estimated_first_goal_minute=calibrated.get("display_estimated_first_goal_minute"),
            bucket_representative_minute=calibrated.get("bucket_representative_minute"),
            weighted_average_minute=calibrated.get("weighted_average_minute"),
            model_confidence_score=model_confidence,
            home_team_goal_probability_by_range=calibrated.get("home_range_probs", {}),
            away_team_goal_probability_by_range=calibrated.get("away_range_probs", {}),
            no_goal_before_minute_probability=calibrated.get("no_goal_probs", {}),
            confidence_score=confidence,
            data_quality_score=data_quality,
            explanation=explanation,
            specialist_agent_breakdown=agent_breakdown,
            model_version=GOAL_TIMING_MODEL_VERSION,
            no_prediction_flag=no_prediction,
            no_bet_flag=no_prediction or confidence < 0.5,
            predicted_at=datetime.now(timezone.utc),
        )

    def foundation_status(self) -> dict[str, Any]:
        return {
            "status": "active",
            "phase": "51D",
            "model_version": GOAL_TIMING_MODEL_VERSION,
            "minute_ranges": list(GOAL_TIMING_MINUTE_RANGES),
            "prediction_leagues": list(GOAL_TIMING_PREDICTION_LEAGUE_KEYS),
            "agents": list(self.agent_orchestrator.agent_keys),
            "api_quota_policy": "stored_only_default",
            "message": (
                "Elite Goal Timing baseline model is active for Premier League. "
                "Predictions use stored goal-minute history without API quota by default."
            ),
        }
