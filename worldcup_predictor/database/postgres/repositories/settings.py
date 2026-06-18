"""PostgreSQL user settings repository."""

from __future__ import annotations

import uuid
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any

from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.models import UserSettings
from worldcup_predictor.database.postgres.schemas import UserSettingsRecord


def _to_record(row: UserSettings) -> UserSettingsRecord:
    return UserSettingsRecord(
        user_id=row.user_id,
        language=row.language,
        timezone=row.timezone,
        preferences=dict(row.preferences or {}),
        updated_at=row.updated_at,
    )


class UserSettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID) -> UserSettingsRecord | None:
        row = self._session.get(UserSettings, user_id)
        return _to_record(row) if row else None

    def get_or_create(self, user_id: uuid.UUID) -> UserSettingsRecord:
        row = self._session.get(UserSettings, user_id)
        if row is None:
            row = UserSettings(user_id=user_id)
            self._session.add(row)
            self._session.flush()
        return _to_record(row)

    def upsert(
        self,
        user_id: uuid.UUID,
        *,
        language: str | None = None,
        timezone: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> UserSettingsRecord:
        row = self._session.get(UserSettings, user_id)
        if row is None:
            row = UserSettings(user_id=user_id)
            self._session.add(row)
        if language is not None:
            row.language = language
        if timezone is not None:
            row.timezone = timezone
        if preferences is not None:
            row.preferences = preferences
        row.updated_at = datetime.now(dt_timezone.utc)
        self._session.flush()
        return _to_record(row)
