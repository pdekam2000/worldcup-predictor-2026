"""PostgreSQL user repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
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
        is_banned=row.is_banned,
        banned_at=row.banned_at,
        banned_reason=row.banned_reason,
        token_version=int(row.token_version or 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_login_at=row.last_login_at,
    )


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _touch_updated(self, row: User) -> None:
        row.updated_at = datetime.now(timezone.utc)

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
        self._touch_updated(row)
        self._session.flush()

    def create(
        self,
        *,
        email: str,
        password_hash: str = "",
        full_name: str | None = None,
        role: UserRole = UserRole.USER,
        email_verified: bool = False,
    ) -> UserRecord:
        row = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            email_verified=email_verified,
        )
        self._session.add(row)
        self._session.flush()
        return _to_record(row)

    def touch_login(self, user_id: uuid.UUID) -> None:
        row = self._session.get(User, user_id)
        if row is None:
            return
        row.last_login_at = datetime.now(timezone.utc)
        self._touch_updated(row)
        self._session.flush()

    def set_role(self, user_id: uuid.UUID, role: UserRole) -> UserRecord | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.role = role
        self._touch_updated(row)
        self._session.flush()
        return _to_record(row)

    def set_email_verified(self, user_id: uuid.UUID, verified: bool = True) -> UserRecord | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.email_verified = verified
        self._touch_updated(row)
        self._session.flush()
        return _to_record(row)

    def set_active(self, user_id: uuid.UUID, active: bool) -> UserRecord | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.is_active = active
        self._touch_updated(row)
        self._session.flush()
        return _to_record(row)

    def set_banned(self, user_id: uuid.UUID, *, reason: str | None = None) -> UserRecord | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.is_banned = True
        row.is_active = False
        row.banned_at = datetime.now(timezone.utc)
        row.banned_reason = (reason or "").strip() or None
        self._touch_updated(row)
        self._session.flush()
        return _to_record(row)

    def clear_ban(self, user_id: uuid.UUID) -> UserRecord | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.is_banned = False
        row.is_active = True
        row.banned_at = None
        row.banned_reason = None
        self._touch_updated(row)
        self._session.flush()
        return _to_record(row)

    def bump_token_version(self, user_id: uuid.UUID) -> int | None:
        row = self._session.get(User, user_id)
        if row is None:
            return None
        row.token_version = int(row.token_version or 0) + 1
        self._touch_updated(row)
        self._session.flush()
        return int(row.token_version)

    def count_by_role(self, role: UserRole) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(User).where(User.role == role)) or 0
        )

    def list_users(self, *, limit: int = 50, offset: int = 0) -> list[UserRecord]:
        rows = self._session.scalars(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return [_to_record(row) for row in rows]

    def delete_all_users(self) -> int:
        from sqlalchemy import text

        count = int(self._session.scalar(select(func.count()).select_from(User)) or 0)
        for table in (
            "email_verification_tokens",
            "password_reset_tokens",
            "user_prediction_history",
            "user_notifications",
            "user_alerts",
            "user_favorites",
            "billing_invoices",
            "subscriptions",
            "user_settings",
        ):
            self._session.execute(text(f"DELETE FROM {table}"))
        self._session.execute(text("DELETE FROM users"))
        self._session.flush()
        return count
