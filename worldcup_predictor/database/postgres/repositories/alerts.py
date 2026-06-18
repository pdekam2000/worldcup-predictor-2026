"""PostgreSQL alerts repository."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import AlertType
from worldcup_predictor.database.postgres.models import UserAlert
from worldcup_predictor.database.postgres.schemas import AlertRecord


def _to_record(row: UserAlert) -> AlertRecord:
    return AlertRecord(
        id=row.id,
        user_id=row.user_id,
        type=row.type,
        title=row.title,
        message=row.message,
        match_id=row.match_id,
        confidence=row.confidence,
        is_read=row.is_read,
        created_at=row.created_at,
    )


class AlertsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID, *, limit: int = 100) -> list[AlertRecord]:
        rows = self._session.scalars(
            select(UserAlert)
            .where(UserAlert.user_id == user_id)
            .order_by(UserAlert.created_at.desc())
            .limit(limit)
        ).all()
        return [_to_record(row) for row in rows]

    def create(
        self,
        user_id: uuid.UUID,
        *,
        type: AlertType,
        title: str,
        message: str,
        match_id: int | None = None,
        confidence: Decimal | None = None,
    ) -> AlertRecord:
        row = UserAlert(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            match_id=match_id,
            confidence=confidence,
        )
        self._session.add(row)
        self._session.flush()
        return _to_record(row)

    def mark_read(self, user_id: uuid.UUID, alert_id: uuid.UUID) -> bool:
        row = self._session.get(UserAlert, alert_id)
        if row is None or row.user_id != user_id:
            return False
        row.is_read = True
        self._session.flush()
        return True

    def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = self._session.execute(
            update(UserAlert)
            .where(UserAlert.user_id == user_id, UserAlert.is_read.is_(False))
            .values(is_read=True)
        )
        self._session.flush()
        return int(result.rowcount or 0)
