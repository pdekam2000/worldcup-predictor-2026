"""Email verification token repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.models import EmailVerificationToken


class EmailVerificationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> uuid.UUID:
        row = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def get_valid_by_hash(self, token_hash: str) -> EmailVerificationToken | None:
        now = datetime.now(timezone.utc)
        return self._session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > now,
            )
        )

    def mark_used(self, token_id: uuid.UUID) -> None:
        row = self._session.get(EmailVerificationToken, token_id)
        if row is None:
            return
        row.used_at = datetime.now(timezone.utc)
        self._session.flush()

    def invalidate_for_user(self, user_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        rows = self._session.scalars(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.used_at.is_(None),
            )
        ).all()
        for row in rows:
            row.used_at = now
        self._session.flush()
