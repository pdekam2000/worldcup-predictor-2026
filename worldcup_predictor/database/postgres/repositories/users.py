"""PostgreSQL user repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from worldcup_predictor.database.postgres.enums import UserRole
from worldcup_predictor.database.postgres.models import User
from worldcup_predictor.database.postgres.schemas import UserRecord


def _to_record(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        role=row.role,
        is_active=row.is_active,
        email_verified=row.email_verified,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: uuid.UUID) -> UserRecord | None:
        row = self._session.get(User, user_id)
        return _to_record(row) if row else None

    def get_by_email(self, email: str) -> UserRecord | None:
        normalized = email.strip().lower()
        row = self._session.scalar(select(User).where(User.email == normalized))
        return _to_record(row) if row else None

    def get_password_hash(self, email: str) -> str | None:
        normalized = email.strip().lower()
        row = self._session.scalar(select(User).where(User.email == normalized))
        return row.password_hash if row else None

    def verify_email_password(self, email: str, password: str, verify_fn) -> UserRecord | None:
        normalized = email.strip().lower()
        row = self._session.scalar(select(User).where(User.email == normalized))
        if row is None or not verify_fn(password, row.password_hash):
            return None
        return _to_record(row)

    def update_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        row = self._session.get(User, user_id)
        if row is None:
            return
        row.password_hash = password_hash
        self._session.flush()

    def create(
        self,
        *,
        email: str,
        password_hash: str = "",
        full_name: str | None = None,
        role: UserRole = UserRole.USER,
    ) -> UserRecord:
        row = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            full_name=full_name,
            role=role,
        )
        self._session.add(row)
        self._session.flush()
        return _to_record(row)

    def touch_login(self, user_id: uuid.UUID) -> None:
        row = self._session.get(User, user_id)
        if row is None:
            return
        row.last_login_at = datetime.now(timezone.utc)
        self._session.flush()

    def set_role(self, user_id: uuid.UUID, role: UserRole) -> UserRecord | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.role = role
        self._session.flush()
        return _to_record(row)

    def list_users(self, *, limit: int = 50, offset: int = 0) -> list[UserRecord]:
        rows = self._session.scalars(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return [_to_record(row) for row in rows]
