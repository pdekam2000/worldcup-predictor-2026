"""Social share link store — Phase A20."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _new_share_id() -> str:
    return secrets.token_urlsafe(12)


class SocialShareStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._conn: sqlite3.Connection = self._repo._conn  # noqa: SLF001
        ensure_schema_compat(self._conn)

    def create_share(
        self,
        *,
        share_type: str,
        payload: dict[str, Any],
        user_id: str | None = None,
        og_title: str | None = None,
        og_description: str | None = None,
        opt_in: bool = False,
        ttl_days: int = 90,
    ) -> dict[str, Any]:
        share_id = _new_share_id()
        now = _utc_now()
        expires = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).replace(tzinfo=None).isoformat()
        self._conn.execute(
            """
            INSERT INTO social_share_links (
                share_id, user_id, share_type, payload_json, og_title, og_description,
                is_public, opt_in, expires_at, created_at, view_count
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 0)
            """,
            (
                share_id,
                user_id,
                share_type,
                json.dumps(payload, separators=(",", ":"), default=str),
                og_title,
                og_description,
                1 if opt_in else 0,
                expires,
                now,
            ),
        )
        self._conn.commit()
        return self.get_share(share_id) or {"share_id": share_id}

    def get_share(self, share_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM social_share_links WHERE share_id = ? AND is_public = 1",
            (share_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        if item.get("expires_at") and str(item["expires_at"]) < _utc_now():
            return None
        try:
            item["payload"] = json.loads(item.pop("payload_json", "{}") or "{}")
        except json.JSONDecodeError:
            item["payload"] = {}
        # Never expose user_id on public read
        item.pop("user_id", None)
        self._conn.execute(
            "UPDATE social_share_links SET view_count = view_count + 1 WHERE share_id = ?",
            (share_id,),
        )
        self._conn.commit()
        return item
