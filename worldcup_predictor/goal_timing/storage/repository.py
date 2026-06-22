"""PostgreSQL persistence for goal timing engine."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.goal_timing.models import GoalTimingAgentOutput, GoalTimingPredictionResult

logger = logging.getLogger(__name__)


class GoalTimingRepository:
    """CRUD for goal_timing_* PostgreSQL tables."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def save_feature_snapshot(
        self,
        *,
        fixture_id: int,
        as_of: str,
        features: dict[str, Any],
        source_manifest: dict[str, Any],
        competition_key: str = "premier_league",
    ) -> str | None:
        if not postgres_configured(self.settings):
            logger.warning("PostgreSQL not configured — skipping goal_timing_features persist")
            return None

        snapshot_id = uuid.uuid4()
        try:
            as_of_dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        except ValueError:
            as_of_dt = datetime.now(timezone.utc)

        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO goal_timing_features (
                        id, fixture_id, competition_key, as_of, features, source_manifest, created_at
                    ) VALUES (
                        :id, :fixture_id, :competition_key, :as_of, CAST(:features AS jsonb),
                        CAST(:source_manifest AS jsonb), NOW()
                    )
                    """
                ),
                {
                    "id": snapshot_id,
                    "fixture_id": int(fixture_id),
                    "competition_key": competition_key,
                    "as_of": as_of_dt,
                    "features": json.dumps(features, ensure_ascii=False),
                    "source_manifest": json.dumps(source_manifest, ensure_ascii=False),
                },
            )
        return str(snapshot_id)

    def save_prediction(
        self,
        result: GoalTimingPredictionResult,
        *,
        agent_outputs: dict[str, GoalTimingAgentOutput] | None = None,
        feature_snapshot_id: str | None = None,
    ) -> uuid.UUID | None:
        if not postgres_configured(self.settings):
            logger.warning("PostgreSQL not configured — skipping goal_timing_predictions persist")
            return None

        prediction_id = uuid.uuid4()
        snap_uuid = None
        if feature_snapshot_id:
            try:
                snap_uuid = uuid.UUID(str(feature_snapshot_id))
            except ValueError:
                snap_uuid = None

        predicted_at = result.predicted_at or datetime.now(timezone.utc)
        match_date = result.match_date

        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO goal_timing_predictions (
                        id, fixture_id, competition_key, home_team, away_team, match_date,
                        predicted_at, first_goal_team, first_goal_time_range, estimated_first_goal_minute,
                        display_estimated_first_goal_minute, bucket_representative_minute,
                        weighted_average_minute, model_confidence_score,
                        home_team_goal_probability_by_range, away_team_goal_probability_by_range,
                        no_goal_before_minute_probability, confidence_score, data_quality_score,
                        explanation, specialist_agent_breakdown, model_version,
                        no_prediction_flag, no_bet_flag, feature_snapshot_id, status,
                        created_at, updated_at
                    ) VALUES (
                        :id, :fixture_id, :competition_key, :home_team, :away_team, :match_date,
                        :predicted_at, :first_goal_team, :first_goal_time_range, :estimated_first_goal_minute,
                        :display_estimated_first_goal_minute, :bucket_representative_minute,
                        :weighted_average_minute, :model_confidence_score,
                        CAST(:home_probs AS jsonb), CAST(:away_probs AS jsonb),
                        CAST(:no_goal_probs AS jsonb), :confidence_score, :data_quality_score,
                        :explanation, CAST(:agent_breakdown AS jsonb), :model_version,
                        :no_prediction_flag, :no_bet_flag, :feature_snapshot_id, 'published',
                        NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": prediction_id,
                    "fixture_id": int(result.fixture_id),
                    "competition_key": result.competition_key,
                    "home_team": result.home_team,
                    "away_team": result.away_team,
                    "match_date": match_date,
                    "predicted_at": predicted_at,
                    "first_goal_team": result.first_goal_team,
                    "first_goal_time_range": result.first_goal_time_range,
                    "estimated_first_goal_minute": result.display_estimated_first_goal_minute,
                    "display_estimated_first_goal_minute": result.display_estimated_first_goal_minute,
                    "bucket_representative_minute": result.bucket_representative_minute,
                    "weighted_average_minute": result.weighted_average_minute,
                    "model_confidence_score": result.model_confidence_score,
                    "home_probs": json.dumps(result.home_team_goal_probability_by_range),
                    "away_probs": json.dumps(result.away_team_goal_probability_by_range),
                    "no_goal_probs": json.dumps(result.no_goal_before_minute_probability),
                    "confidence_score": result.confidence_score,
                    "data_quality_score": result.data_quality_score,
                    "explanation": result.explanation,
                    "agent_breakdown": json.dumps(result.specialist_agent_breakdown, ensure_ascii=False),
                    "model_version": result.model_version,
                    "no_prediction_flag": result.no_prediction_flag,
                    "no_bet_flag": result.no_bet_flag,
                    "feature_snapshot_id": snap_uuid,
                },
            )

            markets = [
                ("first_goal_team", result.first_goal_team, None, result.confidence_score),
                ("first_goal_time_range", result.first_goal_time_range, None, result.confidence_score),
            ]
            match_probs = result.specialist_agent_breakdown.get("match_first_goal_range_probs") or {}
            if isinstance(match_probs, dict):
                for rng, prob in match_probs.items():
                    markets.append(("first_goal_time_range_prob", str(rng), float(prob), result.confidence_score))

            for market_key, predicted_value, probability, confidence in markets:
                session.execute(
                    text(
                        """
                        INSERT INTO goal_timing_prediction_markets (
                            id, prediction_id, market_key, predicted_value, probability, confidence, created_at
                        ) VALUES (
                            :id, :prediction_id, :market_key, :predicted_value, :probability, :confidence, NOW()
                        )
                        ON CONFLICT (prediction_id, market_key) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "prediction_id": prediction_id,
                        "market_key": market_key,
                        "predicted_value": predicted_value,
                        "probability": probability,
                        "confidence": confidence,
                    },
                )

            outputs = agent_outputs or {}
            for agent_name, output in outputs.items():
                payload = output.to_dict() if hasattr(output, "to_dict") else output
                session.execute(
                    text(
                        """
                        INSERT INTO goal_timing_agent_outputs (
                            id, prediction_id, agent_name, status, signals, impact_score, missing_data, created_at
                        ) VALUES (
                            :id, :prediction_id, :agent_name, :status,
                            CAST(:signals AS jsonb), :impact_score, CAST(:missing_data AS jsonb), NOW()
                        )
                        ON CONFLICT (prediction_id, agent_name) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "prediction_id": prediction_id,
                        "agent_name": agent_name,
                        "status": payload.get("status", "limited"),
                        "signals": json.dumps(payload.get("signals") or {}, ensure_ascii=False),
                        "impact_score": payload.get("impact_score"),
                        "missing_data": json.dumps(payload.get("missing_data") or [], ensure_ascii=False),
                    },
                )

        return prediction_id

    def get_prediction_by_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        if not postgres_configured(self.settings):
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text(
                    """
                    SELECT *
                    FROM goal_timing_predictions
                    WHERE fixture_id = :fixture_id
                    ORDER BY predicted_at DESC
                    LIMIT 1
                    """
                ),
                {"fixture_id": int(fixture_id)},
            ).mappings().first()
        return dict(row) if row else None

    def list_predictions(
        self,
        *,
        competition_key: str | None = None,
        limit: int = 50,
        offset: int = 0,
        upcoming_only: bool = False,
    ) -> list[dict[str, Any]]:
        if not postgres_configured(self.settings):
            return []

        query = """
            SELECT *
            FROM goal_timing_predictions
            WHERE no_prediction_flag = false
        """
        params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        if competition_key:
            query += " AND competition_key = :competition_key"
            params["competition_key"] = competition_key
        if upcoming_only:
            query += " AND (match_date IS NULL OR match_date >= NOW())"
        query += " ORDER BY match_date ASC NULLS LAST, predicted_at DESC LIMIT :limit OFFSET :offset"

        with session_scope(self.settings) as session:
            rows = session.execute(text(query), params).mappings().all()
        return [dict(r) for r in rows]
