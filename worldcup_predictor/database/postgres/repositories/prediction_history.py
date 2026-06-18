"""PostgreSQL user prediction history repository."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import Prediction1x2, PredictionResult
from worldcup_predictor.database.postgres.models import UserPredictionHistory
from worldcup_predictor.database.postgres.schemas import PredictionHistoryRecord


def _to_record(row: UserPredictionHistory) -> PredictionHistoryRecord:
    return PredictionHistoryRecord(
        id=row.id,
        user_id=row.user_id,
        fixture_id=row.fixture_id,
        prediction_id=row.prediction_id,
        home_team=row.home_team,
        away_team=row.away_team,
        league=row.league,
        match_date=row.match_date,
        prediction_1x2=row.prediction_1x2,
        confidence=row.confidence,
        result=row.result,
        viewed_at=row.viewed_at,
    )


class PredictionHistoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0) -> list[PredictionHistoryRecord]:
        rows = self._session.scalars(
            select(UserPredictionHistory)
            .where(UserPredictionHistory.user_id == user_id)
            .order_by(UserPredictionHistory.viewed_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_record(row) for row in rows]

    def add(
        self,
        user_id: uuid.UUID,
        *,
        fixture_id: int,
        home_team: str,
        away_team: str,
        prediction_1x2: Prediction1x2,
        prediction_id: str | None = None,
        league: str | None = None,
        match_date: datetime | None = None,
        confidence: Decimal | None = None,
        result: PredictionResult = PredictionResult.PENDING,
    ) -> PredictionHistoryRecord:
        row = UserPredictionHistory(
            user_id=user_id,
            fixture_id=fixture_id,
            prediction_id=prediction_id,
            home_team=home_team,
            away_team=away_team,
            league=league,
            match_date=match_date,
            prediction_1x2=prediction_1x2,
            confidence=confidence,
            result=result,
        )
        self._session.add(row)
        self._session.flush()
        return _to_record(row)
