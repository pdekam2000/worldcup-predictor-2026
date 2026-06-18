"""PostgreSQL notifications repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import NotificationType
from worldcup_predictor.database.postgres.models import UserNotification
from worldcup_predictor.database.postgres.schemas import NotificationRecord


def _to_record(row: UserNotification) -> NotificationRecord:
    return NotificationRecord(
        id=row.id,
        user_id=row.user_id,
        type=row.type,
        title=row.title,
        message=row.message,
        link=row.link,
        is_read=row.is_read,
        created_at=row.created_at,
    )


class NotificationsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: uuid.UUID, *, limit: int = 100) -> list[NotificationRecord]:
        rows = self._session.scalars(
            select(UserNotification)
            .where(UserNotification.user_id == user_id)
            .order_by(UserNotification.created_at.desc())
            .limit(limit)
        ).all()
        return [_to_record(row) for row in rows]

    def create(
        self,
        user_id: uuid.UUID,
        *,
        type: NotificationType,
        title: str,
        message: str,
        link: str | None = None,
    ) -> NotificationRecord:
        row = UserNotification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            link=link,
        )
        self._session.add(row)
        self._session.flush()
        return _to_record(row)

    def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        row = self._session.get(UserNotification, notification_id)
        if row is None or row.user_id != user_id:
            return False
        row.is_read = True
        self._session.flush()
        return True

    def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = self._session.execute(
            update(UserNotification)
            .where(UserNotification.user_id == user_id, UserNotification.is_read.is_(False))
            .values(is_read=True)
        )
        self._session.flush()
        return int(result.rowcount or 0)
