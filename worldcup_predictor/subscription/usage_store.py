"""Monthly prediction usage tracking — Phase 38A."""

from __future__ import annotations

from datetime import datetime, timezone

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.subscription.billing_period import BillingPeriod, resolve_billing_period

_USAGE_DDL = """
CREATE TABLE IF NOT EXISTS user_prediction_usage (
    user_id TEXT NOT NULL,
    billing_period TEXT NOT NULL,
    fixture_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, billing_period, fixture_id)
)
"""

_DAILY_DDL = """
CREATE TABLE IF NOT EXISTS user_daily_prediction_usage (
    user_id TEXT NOT NULL,
    usage_date TEXT NOT NULL,
    fixture_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, usage_date, fixture_id)
)
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


class PredictionUsageStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self._settings.sqlite_path or None)
        self._repo._conn.execute(_USAGE_DDL)
        self._repo._conn.execute(_DAILY_DDL)
        self._repo._conn.commit()

    def billing_period(self, anchor: datetime | None) -> BillingPeriod:
        return resolve_billing_period(anchor)

    def count_period(self, user_id: str, period_key: str) -> int:
        row = self._repo._conn.execute(
            """
            SELECT COUNT(*) AS c FROM user_prediction_usage
            WHERE user_id = ? AND billing_period = ?
            """,
            (str(user_id), period_key),
        ).fetchone()
        return int(row["c"]) if row else 0

    def has_fixture_period(self, user_id: str, period_key: str, fixture_id: int) -> bool:
        row = self._repo._conn.execute(
            """
            SELECT 1 FROM user_prediction_usage
            WHERE user_id = ? AND billing_period = ? AND fixture_id = ?
            """,
            (str(user_id), period_key, int(fixture_id)),
        ).fetchone()
        return row is not None

    def record(self, user_id: str, fixture_id: int, *, period_key: str) -> None:
        self._repo._conn.execute(
            """
            INSERT OR IGNORE INTO user_prediction_usage
                (user_id, billing_period, fixture_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(user_id), period_key, int(fixture_id), _utc_now()),
        )
        self._repo._conn.commit()

    def reset_period(self, user_id: str, period_key: str) -> int:
        cur = self._repo._conn.execute(
            """
            DELETE FROM user_prediction_usage
            WHERE user_id = ? AND billing_period = ?
            """,
            (str(user_id), period_key),
        )
        self._repo._conn.commit()
        return int(cur.rowcount or 0)

    def list_period_usage(self, user_id: str, period_key: str) -> list[dict]:
        rows = self._repo._conn.execute(
            """
            SELECT fixture_id, created_at FROM user_prediction_usage
            WHERE user_id = ? AND billing_period = ?
            ORDER BY created_at DESC
            """,
            (str(user_id), period_key),
        ).fetchall()
        return [{"fixture_id": r["fixture_id"], "created_at": r["created_at"]} for r in rows]

    def count_today(self, user_id: str) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = self._repo._conn.execute(
            "SELECT COUNT(*) AS c FROM user_daily_prediction_usage WHERE user_id = ? AND usage_date = ?",
            (str(user_id), today),
        ).fetchone()
        return int(row["c"]) if row else 0

    def has_fixture_today(self, user_id: str, fixture_id: int) -> bool:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = self._repo._conn.execute(
            "SELECT 1 FROM user_daily_prediction_usage WHERE user_id = ? AND usage_date = ? AND fixture_id = ?",
            (str(user_id), today, int(fixture_id)),
        ).fetchone()
        return row is not None

    def record_daily_legacy(self, user_id: str, fixture_id: int) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._repo._conn.execute(
            """
            INSERT OR IGNORE INTO user_daily_prediction_usage
                (user_id, usage_date, fixture_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(user_id), today, int(fixture_id), _utc_now()),
        )
        self._repo._conn.commit()
