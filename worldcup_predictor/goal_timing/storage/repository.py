"""PostgreSQL persistence for goal timing engine."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.goal_timing.models import (
    GoalTimingAgentOutput,
    GoalTimingEvaluationResult,
    GoalTimingPredictionResult,
)

logger = logging.getLogger(__name__)


def _postgres_read_safe(settings: Settings, default: Any, fn: Any) -> Any:
    """Return default when PostgreSQL is down or unreachable (avoids 500 on dashboard)."""
    if not postgres_configured(settings):
        return default
    try:
        return fn()
    except SQLAlchemyError as exc:
        logger.warning("goal_timing_postgres_read_failed: %s", exc)
        return default


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
        hybrid_confidence_snapshot: dict[str, Any] | None = None,
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
        range_value = result.first_goal_time_range or "unavailable"

        hybrid_json = (
            json.dumps(hybrid_confidence_snapshot, ensure_ascii=False)
            if hybrid_confidence_snapshot
            else None
        )

        with session_scope(self.settings) as session:
            existing = session.execute(
                text(
                    """
                    SELECT id FROM goal_timing_predictions
                    WHERE fixture_id = :fixture_id
                    ORDER BY predicted_at DESC
                    LIMIT 1
                    """
                ),
                {"fixture_id": int(result.fixture_id)},
            ).mappings().first()

            if existing:
                prediction_id = existing["id"]
                session.execute(
                    text(
                        """
                        UPDATE goal_timing_predictions SET
                            competition_key = :competition_key,
                            home_team = :home_team,
                            away_team = :away_team,
                            match_date = :match_date,
                            predicted_at = :predicted_at,
                            first_goal_team = :first_goal_team,
                            first_goal_time_range = :first_goal_time_range,
                            estimated_first_goal_minute = :estimated_first_goal_minute,
                            display_estimated_first_goal_minute = :display_estimated_first_goal_minute,
                            bucket_representative_minute = :bucket_representative_minute,
                            weighted_average_minute = :weighted_average_minute,
                            model_confidence_score = :model_confidence_score,
                            home_team_goal_probability_by_range = CAST(:home_probs AS jsonb),
                            away_team_goal_probability_by_range = CAST(:away_probs AS jsonb),
                            no_goal_before_minute_probability = CAST(:no_goal_probs AS jsonb),
                            confidence_score = :confidence_score,
                            data_quality_score = :data_quality_score,
                            explanation = :explanation,
                            specialist_agent_breakdown = CAST(:agent_breakdown AS jsonb),
                            model_version = :model_version,
                            no_prediction_flag = :no_prediction_flag,
                            no_bet_flag = :no_bet_flag,
                            feature_snapshot_id = :feature_snapshot_id,
                            hybrid_confidence_snapshot = CAST(:hybrid_confidence_snapshot AS jsonb),
                            updated_at = NOW()
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": prediction_id,
                        "competition_key": result.competition_key,
                        "home_team": result.home_team,
                        "away_team": result.away_team,
                        "match_date": match_date,
                        "predicted_at": predicted_at,
                        "first_goal_team": result.first_goal_team,
                        "first_goal_time_range": range_value,
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
                        "hybrid_confidence_snapshot": hybrid_json or "null",
                    },
                )
            else:
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
                            hybrid_confidence_snapshot,
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
                            CAST(:hybrid_confidence_snapshot AS jsonb),
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
                        "first_goal_time_range": range_value,
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
                        "hybrid_confidence_snapshot": hybrid_json or "null",
                    },
                )

            markets = [
                ("first_goal_team", result.first_goal_team, None, result.confidence_score),
                ("first_goal_time_range", range_value, None, result.confidence_score),
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

        def _run() -> dict[str, Any] | None:
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

        return _postgres_read_safe(self.settings, None, _run)

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

        def _run() -> list[dict[str, Any]]:
            with session_scope(self.settings) as session:
                rows = session.execute(text(query), params).mappings().all()
            return [dict(r) for r in rows]

        return _postgres_read_safe(self.settings, [], _run)

    def list_published_predictions(
        self,
        *,
        competition_key: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """All published picks (upcoming and finished) for evaluation refresh."""
        return self.list_predictions(
            competition_key=competition_key,
            limit=limit,
            offset=offset,
            upcoming_only=False,
        )

    def save_evaluation(self, result: GoalTimingEvaluationResult) -> str | None:
        if not postgres_configured(self.settings):
            logger.warning("PostgreSQL not configured — skipping goal_timing_evaluations persist")
            return None

        eval_id = uuid.uuid4()
        evaluated_at = result.evaluated_at or datetime.now(timezone.utc)
        try:
            prediction_uuid = uuid.UUID(str(result.prediction_id))
        except ValueError:
            logger.warning("Invalid prediction_id for evaluation: %s", result.prediction_id)
            return None

        with session_scope(self.settings) as session:
            session.execute(
                text(
                    """
                    INSERT INTO goal_timing_evaluations (
                        id, prediction_id, fixture_id,
                        actual_first_goal_team, actual_first_goal_minute, actual_first_goal_time_range,
                        first_goal_team_status, time_range_status, minute_tolerance_status,
                        evaluated_at
                    ) VALUES (
                        :id, :prediction_id, :fixture_id,
                        :actual_first_goal_team, :actual_first_goal_minute, :actual_first_goal_time_range,
                        :first_goal_team_status, :time_range_status, :minute_tolerance_status,
                        :evaluated_at
                    )
                    ON CONFLICT (prediction_id) DO UPDATE SET
                        fixture_id = EXCLUDED.fixture_id,
                        actual_first_goal_team = EXCLUDED.actual_first_goal_team,
                        actual_first_goal_minute = EXCLUDED.actual_first_goal_minute,
                        actual_first_goal_time_range = EXCLUDED.actual_first_goal_time_range,
                        first_goal_team_status = EXCLUDED.first_goal_team_status,
                        time_range_status = EXCLUDED.time_range_status,
                        minute_tolerance_status = EXCLUDED.minute_tolerance_status,
                        evaluated_at = EXCLUDED.evaluated_at
                    """
                ),
                {
                    "id": eval_id,
                    "prediction_id": prediction_uuid,
                    "fixture_id": int(result.fixture_id),
                    "actual_first_goal_team": result.actual_first_goal_team,
                    "actual_first_goal_minute": result.actual_first_goal_minute,
                    "actual_first_goal_time_range": result.actual_first_goal_time_range,
                    "first_goal_team_status": result.first_goal_team_status,
                    "time_range_status": result.time_range_status,
                    "minute_tolerance_status": result.minute_tolerance_status,
                    "evaluated_at": evaluated_at,
                },
            )
        return str(eval_id)

    def get_evaluation_by_prediction_id(self, prediction_id: str) -> dict[str, Any] | None:
        if not postgres_configured(self.settings):
            return None
        try:
            pred_uuid = uuid.UUID(str(prediction_id))
        except ValueError:
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text(
                    """
                    SELECT *
                    FROM goal_timing_evaluations
                    WHERE prediction_id = :prediction_id
                    LIMIT 1
                    """
                ),
                {"prediction_id": pred_uuid},
            ).mappings().first()
        return dict(row) if row else None

    def get_evaluation_by_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        if not postgres_configured(self.settings):
            return None
        with session_scope(self.settings) as session:
            row = session.execute(
                text(
                    """
                    SELECT e.*
                    FROM goal_timing_evaluations e
                    JOIN goal_timing_predictions p ON p.id = e.prediction_id
                    WHERE e.fixture_id = :fixture_id
                    ORDER BY e.evaluated_at DESC
                    LIMIT 1
                    """
                ),
                {"fixture_id": int(fixture_id)},
            ).mappings().first()
        return dict(row) if row else None

    def list_evaluations_joined(
        self,
        *,
        competition_key: str | None = None,
        limit: int = 50,
        offset: int = 0,
        evaluated_only: bool = False,
    ) -> list[dict[str, Any]]:
        if not postgres_configured(self.settings):
            return []

        query = """
            SELECT
                e.id AS evaluation_id,
                e.prediction_id,
                e.fixture_id,
                e.actual_first_goal_team,
                e.actual_first_goal_minute,
                e.actual_first_goal_time_range,
                e.first_goal_team_status,
                e.time_range_status,
                e.minute_tolerance_status,
                e.evaluated_at,
                p.competition_key,
                p.home_team,
                p.away_team,
                p.match_date,
                p.first_goal_team,
                p.first_goal_time_range,
                p.display_estimated_first_goal_minute,
                p.estimated_first_goal_minute,
                p.confidence_score,
                p.data_quality_score,
                p.model_version,
                p.hybrid_confidence_snapshot
            FROM goal_timing_evaluations e
            JOIN goal_timing_predictions p ON p.id = e.prediction_id
            WHERE p.no_prediction_flag = false
        """
        params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        if competition_key:
            query += " AND p.competition_key = :competition_key"
            params["competition_key"] = competition_key
        if evaluated_only:
            query += """
                AND (
                    e.first_goal_team_status != 'pending'
                    OR e.time_range_status != 'pending'
                    OR e.minute_tolerance_status != 'pending'
                )
            """
        query += " ORDER BY COALESCE(p.match_date, e.evaluated_at) DESC LIMIT :limit OFFSET :offset"

        def _run() -> list[dict[str, Any]]:
            with session_scope(self.settings) as session:
                rows = session.execute(text(query), params).mappings().all()
            return [dict(r) for r in rows]

        return _postgres_read_safe(self.settings, [], _run)

    def count_evaluations(self, *, competition_key: str | None = None) -> int:
        if not postgres_configured(self.settings):
            return 0
        query = """
            SELECT COUNT(*) AS cnt
            FROM goal_timing_evaluations e
            JOIN goal_timing_predictions p ON p.id = e.prediction_id
            WHERE p.no_prediction_flag = false
        """
        params: dict[str, Any] = {}
        if competition_key:
            query += " AND p.competition_key = :competition_key"
            params["competition_key"] = competition_key

        def _run() -> int:
            with session_scope(self.settings) as session:
                row = session.execute(text(query), params).mappings().first()
            return int(row["cnt"]) if row else 0

        return _postgres_read_safe(self.settings, 0, _run)

    def prediction_monitoring_counts(self) -> dict[str, int]:
        zeros = {
            "published_picks": 0,
            "no_pick_count": 0,
            "evaluated_picks": 0,
            "total_predictions": 0,
        }
        if not postgres_configured(self.settings):
            return zeros

        def _run() -> dict[str, int]:
            with session_scope(self.settings) as session:
                pub = session.execute(
                    text(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM goal_timing_predictions
                        WHERE no_prediction_flag = false
                        """
                    )
                ).mappings().first()
                no_pick = session.execute(
                    text(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM goal_timing_predictions
                        WHERE no_prediction_flag = true
                        """
                    )
                ).mappings().first()
                evaluated = session.execute(
                    text("SELECT COUNT(*) AS cnt FROM goal_timing_evaluations")
                ).mappings().first()
                total = session.execute(
                    text("SELECT COUNT(*) AS cnt FROM goal_timing_predictions")
                ).mappings().first()
            return {
                "published_picks": int(pub["cnt"]) if pub else 0,
                "no_pick_count": int(no_pick["cnt"]) if no_pick else 0,
                "evaluated_picks": int(evaluated["cnt"]) if evaluated else 0,
                "total_predictions": int(total["cnt"]) if total else 0,
            }

        return _postgres_read_safe(self.settings, zeros, _run)

    def list_no_pick_predictions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not postgres_configured(self.settings):
            return []

        def _run() -> list[dict[str, Any]]:
            with session_scope(self.settings) as session:
                rows = session.execute(
                    text(
                        """
                        SELECT fixture_id, home_team, away_team, match_date,
                               data_quality_score, explanation, no_prediction_flag
                        FROM goal_timing_predictions
                        WHERE no_prediction_flag = true
                        ORDER BY match_date ASC NULLS LAST, predicted_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": int(limit)},
                ).mappings().all()
            return [dict(r) for r in rows]

        return _postgres_read_safe(self.settings, [], _run)
