"""SQLite repository for users, limits, entitlements, feedback."""

from __future__ import annotations

import csv
import io
import secrets
import sqlite3
import uuid
from typing import Any

from worldcup_predictor.access.config import access_db_path
from worldcup_predictor.access.models import AppUser, UserEntitlement, UserFeedback, utc_now_iso, utc_today
from worldcup_predictor.access.schema import ACCESS_DDL_STATEMENTS
from worldcup_predictor.database.connection import connect, get_db_path

_repo_singleton: "AccessRepository | None" = None


def get_access_repository(db_path: str | None = None) -> "AccessRepository":
    """Shared repository instance — one DB path per process."""
    global _repo_singleton
    path = db_path or access_db_path()
    if _repo_singleton is None or (path and str(_repo_singleton._path) != str(get_db_path(path))):
        _repo_singleton = AccessRepository(path)
    return _repo_singleton


class AccessRepository:
    """Lightweight access-control persistence — never raises on read paths."""

    def __init__(self, db_path: str | None = None) -> None:
        resolved = db_path or access_db_path()
        self._path = get_db_path(resolved)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self._path)
        return self._conn

    def _ensure_schema(self) -> None:
        try:
            conn = self._connection()
            for ddl in ACCESS_DDL_STATEMENTS:
                conn.execute(ddl)
            conn.commit()
        except sqlite3.Error:
            pass

    def _row_user(self, row: sqlite3.Row | None) -> AppUser | None:
        if row is None:
            return None
        return AppUser(
            user_id=row["user_id"],
            email=row["email"],
            access_token=row["access_token"],
            created_at=row["created_at"],
            is_anonymous=bool(row["is_anonymous"]),
            last_login_at=row["last_login_at"],
        )

    def create_email_user(self, email: str) -> AppUser | None:
        normalized = email.strip().lower()
        if not normalized or "@" not in normalized:
            return None
        token = secrets.token_urlsafe(24)
        user_id = str(uuid.uuid4())
        now = utc_now_iso()
        try:
            conn = self._connection()
            conn.execute(
                """
                INSERT INTO app_users (user_id, email, access_token, created_at, is_anonymous, last_login_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (user_id, normalized, token, now, now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO user_entitlements (user_id, plan, paid)
                VALUES (?, 'free', 0)
                """,
                (user_id,),
            )
            conn.commit()
            return self.get_user_by_id(user_id)
        except sqlite3.IntegrityError:
            return self.get_user_by_email(normalized)
        except sqlite3.Error:
            return None

    def get_or_create_anonymous_user(self, anonymous_id: str) -> AppUser | None:
        user_id = f"anon_{anonymous_id}"
        existing = self.get_user_by_id(user_id)
        if existing:
            return existing
        token = secrets.token_urlsafe(16)
        now = utc_now_iso()
        try:
            conn = self._connection()
            conn.execute(
                """
                INSERT INTO app_users (user_id, email, access_token, created_at, is_anonymous, last_login_at)
                VALUES (?, NULL, ?, ?, 1, ?)
                """,
                (user_id, token, now, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO user_entitlements (user_id, plan, paid) VALUES (?, 'free', 0)",
                (user_id,),
            )
            conn.commit()
            return self.get_user_by_id(user_id)
        except sqlite3.Error:
            return None

    def get_user_by_id(self, user_id: str) -> AppUser | None:
        try:
            row = self._connection().execute(
                "SELECT * FROM app_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return self._row_user(row)
        except sqlite3.Error:
            return None

    def get_user_by_email(self, email: str) -> AppUser | None:
        try:
            row = self._connection().execute(
                "SELECT * FROM app_users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
            return self._row_user(row)
        except sqlite3.Error:
            return None

    def authenticate(self, *, email: str | None = None, access_token: str | None = None) -> AppUser | None:
        token = (access_token or "").strip()
        if not token:
            return None
        try:
            if email:
                row = self._connection().execute(
                    "SELECT * FROM app_users WHERE email = ? AND access_token = ?",
                    (email.strip().lower(), token),
                ).fetchone()
            else:
                row = self._connection().execute(
                    "SELECT * FROM app_users WHERE access_token = ?",
                    (token,),
                ).fetchone()
            user = self._row_user(row)
            if user:
                self._touch_login(user.user_id)
            return user
        except sqlite3.Error:
            return None

    def _touch_login(self, user_id: str) -> None:
        try:
            conn = self._connection()
            conn.execute(
                "UPDATE app_users SET last_login_at = ? WHERE user_id = ?",
                (utc_now_iso(), user_id),
            )
            conn.commit()
        except sqlite3.Error:
            pass

    def touch_login(self, user_id: str) -> None:
        """Public wrapper for login timestamp update."""
        self._touch_login(user_id)

    def search_users(self, query: str, *, limit: int = 25) -> list[AppUser]:
        q = f"%{query.strip().lower()}%"
        try:
            rows = self._connection().execute(
                """
                SELECT * FROM app_users
                WHERE lower(email) LIKE ? OR user_id LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (q, q, limit),
            ).fetchall()
            return [u for row in rows if (u := self._row_user(row))]
        except sqlite3.Error:
            return []

    def get_entitlement(self, user_id: str) -> UserEntitlement:
        try:
            row = self._connection().execute(
                "SELECT * FROM user_entitlements WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                return UserEntitlement(user_id=user_id)
            return UserEntitlement(
                user_id=row["user_id"],
                plan=row["plan"] or "free",
                paid=bool(row["paid"]),
                paid_at=row["paid_at"],
                expires_at=row["expires_at"],
                provider=row["provider"],
                payment_reference=row["payment_reference"],
            )
        except sqlite3.Error:
            return UserEntitlement(user_id=user_id)

    def is_paid(self, user_id: str) -> bool:
        ent = self.get_entitlement(user_id)
        if not ent.paid:
            return False
        if not ent.expires_at:
            return True
        try:
            from datetime import datetime, timezone

            exp = datetime.fromisoformat(ent.expires_at.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return exp > datetime.now(timezone.utc)
        except Exception:
            return True

    def mark_paid(
        self,
        user_id: str,
        *,
        provider: str = "manual",
        payment_reference: str | None = None,
        plan: str = "paid_unlock",
    ) -> bool:
        now = utc_now_iso()
        try:
            conn = self._connection()
            conn.execute(
                """
                INSERT INTO user_entitlements (user_id, plan, paid, paid_at, provider, payment_reference)
                VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    plan = excluded.plan,
                    paid = 1,
                    paid_at = excluded.paid_at,
                    provider = excluded.provider,
                    payment_reference = excluded.payment_reference
                """,
                (user_id, plan, now, provider, payment_reference),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def revoke_paid(self, user_id: str) -> bool:
        try:
            conn = self._connection()
            conn.execute(
                """
                UPDATE user_entitlements
                SET paid = 0, plan = 'free', paid_at = NULL, payment_reference = NULL
                WHERE user_id = ?
                """,
                (user_id,),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def get_usage_count(self, user_id: str, usage_date: str | None = None) -> int:
        day = usage_date or utc_today()
        try:
            row = self._connection().execute(
                "SELECT prediction_count FROM user_usage_limits WHERE user_id = ? AND usage_date = ?",
                (user_id, day),
            ).fetchone()
            return int(row["prediction_count"]) if row else 0
        except sqlite3.Error:
            return 0

    def try_increment_prediction(self, user_id: str, *, daily_limit: int) -> tuple[bool, int]:
        """Atomically increment if under limit. Returns (allowed, new_count)."""
        day = utc_today()
        now = utc_now_iso()
        try:
            conn = self._connection()
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT prediction_count FROM user_usage_limits WHERE user_id = ? AND usage_date = ?",
                (user_id, day),
            ).fetchone()
            current = int(row["prediction_count"]) if row else 0
            if current >= daily_limit:
                conn.execute("ROLLBACK")
                return False, current
            if row is None:
                conn.execute(
                    """
                    INSERT INTO user_usage_limits (user_id, usage_date, prediction_count, last_prediction_at)
                    VALUES (?, ?, 1, ?)
                    """,
                    (user_id, day, now),
                )
                new_count = 1
            else:
                new_count = current + 1
                conn.execute(
                    """
                    UPDATE user_usage_limits
                    SET prediction_count = ?, last_prediction_at = ?
                    WHERE user_id = ? AND usage_date = ?
                    """,
                    (new_count, now, user_id, day),
                )
            conn.commit()
            return True, new_count
        except sqlite3.Error:
            try:
                self._connection().execute("ROLLBACK")
            except Exception:
                pass
            return False, self.get_usage_count(user_id, day)

    def save_feedback(
        self,
        *,
        user_id: str | None,
        rating: int,
        comment: str | None = None,
        fixture_id: int | None = None,
        prediction_context: str | None = None,
    ) -> bool:
        rating = max(1, min(5, int(rating)))
        try:
            conn = self._connection()
            conn.execute(
                """
                INSERT INTO user_feedback (user_id, fixture_id, rating, comment, prediction_context, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, fixture_id, rating, (comment or "").strip() or None, prediction_context, utc_now_iso()),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def list_feedback(self, *, limit: int = 100) -> list[UserFeedback]:
        try:
            rows = self._connection().execute(
                """
                SELECT * FROM user_feedback
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                UserFeedback(
                    id=row["id"],
                    user_id=row["user_id"],
                    fixture_id=row["fixture_id"],
                    rating=row["rating"],
                    comment=row["comment"],
                    prediction_context=row["prediction_context"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
        except sqlite3.Error:
            return []

    def export_feedback_csv(self) -> str:
        rows = self.list_feedback(limit=5000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "user_id", "fixture_id", "rating", "comment", "prediction_context", "created_at"])
        for item in rows:
            writer.writerow(
                [
                    item.id,
                    item.user_id or "",
                    item.fixture_id or "",
                    item.rating,
                    item.comment or "",
                    item.prediction_context or "",
                    item.created_at,
                ]
            )
        return buf.getvalue()
