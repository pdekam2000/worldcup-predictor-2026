"""AI Assistant SQLite store — Phase A19."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.ai_assistant.constants import DEFAULT_PREFERENCES
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class AssistantStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._conn: sqlite3.Connection = self._repo._conn  # noqa: SLF001
        ensure_schema_compat(self._conn)

    # --- Watchlist ---

    def list_watchlist(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM assistant_watchlist WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            if item.get("item_meta"):
                try:
                    item["item_meta"] = json.loads(item["item_meta"])
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out

    def add_watchlist(
        self,
        user_id: str,
        *,
        item_type: str,
        item_id: str,
        item_name: str | None = None,
        item_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        meta_json = json.dumps(item_meta or {}, separators=(",", ":"))
        self._conn.execute(
            """
            INSERT OR REPLACE INTO assistant_watchlist (
                user_id, item_type, item_id, item_name, item_meta, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, item_type, str(item_id), item_name, meta_json, now),
        )
        self._conn.commit()
        row = self._conn.execute(
            """
            SELECT * FROM assistant_watchlist
            WHERE user_id = ? AND item_type = ? AND item_id = ?
            """,
            (user_id, item_type, str(item_id)),
        ).fetchone()
        item = dict(row) if row else {}
        if item.get("item_meta"):
            try:
                item["item_meta"] = json.loads(item["item_meta"])
            except json.JSONDecodeError:
                pass
        return item

    def remove_watchlist(self, user_id: str, watchlist_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM assistant_watchlist WHERE id = ? AND user_id = ?",
            (watchlist_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def users_with_watchlist(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT user_id FROM assistant_watchlist",
        ).fetchall()
        return [str(r[0]) for r in rows]

    def watchlist_for_fixture(self, fixture_id: int) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT user_id FROM assistant_watchlist
            WHERE (item_type = 'fixture' AND item_id = ?)
               OR (item_type = 'competition' AND item_id IN (
                    SELECT competition_key FROM predops_snapshots WHERE fixture_id = ? LIMIT 1
               ))
            """,
            (str(fixture_id), fixture_id),
        ).fetchall()
        return [str(r[0]) for r in rows]

    # --- Preferences ---

    def get_preferences(self, user_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT prefs_json FROM assistant_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return dict(DEFAULT_PREFERENCES)
        try:
            prefs = json.loads(row[0])
        except json.JSONDecodeError:
            prefs = {}
        merged = dict(DEFAULT_PREFERENCES)
        merged.update(prefs)
        return merged

    def upsert_preferences(self, user_id: str, prefs: dict[str, Any]) -> dict[str, Any]:
        current = self.get_preferences(user_id)
        current.update(prefs)
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO assistant_preferences (user_id, prefs_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET prefs_json = excluded.prefs_json, updated_at = excluded.updated_at
            """,
            (user_id, json.dumps(current, separators=(",", ":")), now),
        )
        self._conn.commit()
        return current

    # --- Notifications ---

    def list_notifications(
        self,
        user_id: str,
        *,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if category:
            rows = self._conn.execute(
                """
                SELECT * FROM assistant_notifications
                WHERE user_id = ? AND category = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, category, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM assistant_notifications
                WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def unread_count(self, user_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM assistant_notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    def create_notification(
        self,
        user_id: str,
        *,
        category: str,
        alert_type: str,
        title: str,
        message: str,
        fixture_id: int | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        reason: str | None = None,
        link: str | None = None,
        dedup_key: str | None = None,
    ) -> dict[str, Any] | None:
        if dedup_key and self._is_duplicate(user_id, dedup_key):
            return None
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO assistant_notifications (
                user_id, category, alert_type, fixture_id, title, message,
                old_value, new_value, reason, link, is_read, dedup_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                user_id,
                category,
                alert_type,
                fixture_id,
                title,
                message,
                old_value,
                new_value,
                reason,
                link,
                dedup_key,
                now,
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM assistant_notifications WHERE id = last_insert_rowid()",
        ).fetchone()
        return dict(row) if row else None

    def _is_duplicate(self, user_id: str, dedup_key: str) -> bool:
        from worldcup_predictor.ai_assistant.constants import DEDUP_WINDOW_HOURS

        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)
        ).replace(tzinfo=None).isoformat()
        row = self._conn.execute(
            """
            SELECT 1 FROM assistant_notifications
            WHERE user_id = ? AND dedup_key = ? AND created_at >= ?
            LIMIT 1
            """,
            (user_id, dedup_key, cutoff),
        ).fetchone()
        return row is not None

    def mark_read(self, user_id: str, notification_id: int) -> bool:
        cur = self._conn.execute(
            "UPDATE assistant_notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_all_read(self, user_id: str) -> int:
        cur = self._conn.execute(
            "UPDATE assistant_notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
            (user_id,),
        )
        self._conn.commit()
        return cur.rowcount

    # --- Alert state (dedup / tracking) ---

    def get_alert_state(self, scope_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM assistant_alert_state WHERE scope_key = ?",
            (scope_key,),
        ).fetchone()
        return dict(row) if row else None

    def set_alert_state(
        self,
        scope_key: str,
        *,
        last_value: str | None = None,
        last_snapshot_id: str | None = None,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO assistant_alert_state (scope_key, last_value, last_snapshot_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                last_value = excluded.last_value,
                last_snapshot_id = excluded.last_snapshot_id,
                updated_at = excluded.updated_at
            """,
            (scope_key, last_value, last_snapshot_id, now),
        )
        self._conn.commit()

    def admin_aggregate(self) -> dict[str, Any]:
        users = self._conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM assistant_watchlist",
        ).fetchone()
        notifs = self._conn.execute(
            "SELECT COUNT(*) FROM assistant_notifications",
        ).fetchone()
        by_cat = self._conn.execute(
            """
            SELECT category, COUNT(*) FROM assistant_notifications
            GROUP BY category
            """,
        ).fetchall()
        return {
            "watchlist_users": int(users[0]) if users else 0,
            "total_notifications": int(notifs[0]) if notifs else 0,
            "by_category": {str(r[0]): int(r[1]) for r in by_cat},
        }
