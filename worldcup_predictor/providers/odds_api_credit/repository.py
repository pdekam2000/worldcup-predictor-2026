"""SQLite persistence for The Odds API usage and response cache."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from worldcup_predictor.access.config import access_db_path
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.database.schema import DEFAULT_DB_PATH, DDL_STATEMENTS


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_today() -> str:
    return date.today().isoformat()


def utc_month() -> str:
    return date.today().strftime("%Y-%m")


_repo: "OddsApiRepository | None" = None


def get_odds_api_repository(db_path: str | None = None) -> "OddsApiRepository":
    global _repo
    path = get_db_path(db_path or access_db_path() or DEFAULT_DB_PATH)
    if _repo is None or _repo.path != path:
        _repo = OddsApiRepository(path)
    return _repo


class OddsApiRepository:
    def __init__(self, db_path) -> None:
        self.path = get_db_path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.path)
        return self._conn

    def _ensure_schema(self) -> None:
        try:
            conn = self._connection()
            for ddl in DDL_STATEMENTS:
                conn.execute(ddl)
            conn.commit()
        except sqlite3.Error:
            pass

    def sum_credits_for_date(self, usage_date: str | None = None) -> int:
        day = usage_date or utc_today()
        try:
            row = self._connection().execute(
                "SELECT COALESCE(SUM(credits_used), 0) AS total FROM odds_api_usage WHERE usage_date = ?",
                (day,),
            ).fetchone()
            return int(row["total"]) if row else 0
        except sqlite3.Error:
            return 0

    def sum_credits_for_month(self, usage_month: str | None = None) -> int:
        month = usage_month or utc_month()
        try:
            row = self._connection().execute(
                "SELECT COALESCE(SUM(credits_used), 0) AS total FROM odds_api_usage WHERE usage_month = ?",
                (month,),
            ).fetchone()
            return int(row["total"]) if row else 0
        except sqlite3.Error:
            return 0

    def record_usage(
        self,
        *,
        endpoint: str,
        fixture_id: int | None,
        credits_used: int = 1,
    ) -> None:
        now = utc_now_iso()
        day = utc_today()
        month = utc_month()
        try:
            conn = self._connection()
            conn.execute(
                """
                INSERT INTO odds_api_usage
                (usage_date, usage_month, endpoint, fixture_id, credits_used, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (day, month, endpoint, fixture_id, credits_used, now),
            )
            conn.commit()
        except sqlite3.Error:
            pass

    def get_cache(self, fixture_id: int, market_key: str) -> dict[str, Any] | None:
        try:
            row = self._connection().execute(
                "SELECT response_json, cached_at FROM odds_api_cache WHERE fixture_id = ? AND market_key = ?",
                (fixture_id, market_key),
            ).fetchone()
            if row is None:
                return None
            return {"response_json": row["response_json"], "cached_at": row["cached_at"]}
        except sqlite3.Error:
            return None

    def set_cache(self, fixture_id: int, market_key: str, event: dict[str, Any]) -> None:
        try:
            conn = self._connection()
            conn.execute(
                """
                INSERT INTO odds_api_cache (fixture_id, market_key, response_json, cached_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fixture_id, market_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    cached_at = excluded.cached_at
                """,
                (fixture_id, market_key, json.dumps(event), utc_now_iso()),
            )
            conn.commit()
        except sqlite3.Error:
            pass

    def usage_summary(self) -> dict[str, int]:
        daily = self.sum_credits_for_date()
        monthly = self.sum_credits_for_month()
        return {"daily_used": daily, "monthly_used": monthly}
