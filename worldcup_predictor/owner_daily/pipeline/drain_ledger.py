"""Persistent daily eligible-fixture drain ledger (resume-safe, no secrets)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_DIR = Path("data") / "daily_fixture_drain"
LEDGER_DB = LEDGER_DIR / "ledger.db"

# Queue states (Part C)
DISCOVERED = "DISCOVERED"
ELIGIBLE = "ELIGIBLE"
QUEUED = "QUEUED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FROZEN = "FROZEN"
BLOCKED = "BLOCKED"
FAILED_RETRYABLE = "FAILED_RETRYABLE"
FAILED_FINAL = "FAILED_FINAL"
POST_KICKOFF_SKIPPED = "POST_KICKOFF_SKIPPED"

TERMINAL_STATES = frozenset(
    {
        FROZEN,
        BLOCKED,
        FAILED_FINAL,
        POST_KICKOFF_SKIPPED,
        COMPLETED,  # predicted but freeze pending/partial policy applied
    }
)

ACTIVE_STATES = frozenset({DISCOVERED, ELIGIBLE, QUEUED, RUNNING, FAILED_RETRYABLE})

DEFAULT_MAX_ATTEMPTS = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def idempotency_key(report_date: str, fixture_id: int, scope: str) -> str:
    return f"{report_date}:{int(fixture_id)}:{scope}"


class DrainLedger:
    """SQLite ledger: one row per fixture/date/scope."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or LEDGER_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=60)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DrainLedger:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_fixture_drain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                fixture_id INTEGER NOT NULL,
                scope TEXT NOT NULL,
                competition_key TEXT,
                queue_state TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                job_id TEXT,
                prediction_status TEXT,
                freeze_id TEXT,
                block_reason TEXT,
                failure_code TEXT,
                idempotency_key TEXT NOT NULL UNIQUE,
                kickoff_utc TEXT,
                started_at TEXT,
                finished_at TEXT,
                next_retry_at TEXT,
                component_status_json TEXT,
                meta_json TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drain_date_state
            ON daily_fixture_drain(report_date, queue_state)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drain_date_fixture
            ON daily_fixture_drain(report_date, fixture_id)
            """
        )
        self._conn.commit()

    def upsert_discovered(
        self,
        *,
        report_date: str,
        fixture_id: int,
        scope: str,
        competition_key: str | None,
        kickoff_utc: str | None,
        queue_state: str = DISCOVERED,
        block_reason: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = idempotency_key(report_date, fixture_id, scope)
        existing = self.get_by_key(key)
        now = _utc_now()
        if existing:
            # Do not regress terminal rows on rediscovery
            if existing["queue_state"] in TERMINAL_STATES:
                return existing
            self._conn.execute(
                """
                UPDATE daily_fixture_drain
                SET competition_key=?, kickoff_utc=?, queue_state=?,
                    block_reason=COALESCE(?, block_reason),
                    meta_json=?, updated_at=?
                WHERE idempotency_key=?
                """,
                (
                    competition_key,
                    kickoff_utc,
                    queue_state,
                    block_reason,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                    key,
                ),
            )
            self._conn.commit()
            return self.get_by_key(key) or existing

        self._conn.execute(
            """
            INSERT INTO daily_fixture_drain (
                report_date, fixture_id, scope, competition_key, queue_state,
                attempt_count, max_attempts, block_reason, idempotency_key,
                kickoff_utc, meta_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_date,
                int(fixture_id),
                scope,
                competition_key,
                queue_state,
                DEFAULT_MAX_ATTEMPTS,
                block_reason,
                key,
                kickoff_utc,
                json.dumps(meta or {}, ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()
        return self.get_by_key(key) or {}

    def get_by_key(self, key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM daily_fixture_drain WHERE idempotency_key=?", (key,)
        ).fetchone()
        return dict(row) if row else None

    def list_for_date(self, report_date: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM daily_fixture_drain
            WHERE report_date=?
            ORDER BY kickoff_utc, fixture_id
            """,
            (report_date,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_pending(self, report_date: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM daily_fixture_drain
            WHERE report_date=?
              AND queue_state IN (?, ?, ?, ?)
            ORDER BY kickoff_utc, fixture_id
            """,
            (report_date, ELIGIBLE, QUEUED, RUNNING, FAILED_RETRYABLE),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark(
        self,
        key: str,
        *,
        queue_state: str,
        job_id: str | None = None,
        prediction_status: str | None = None,
        freeze_id: str | None = None,
        block_reason: str | None = None,
        failure_code: str | None = None,
        increment_attempt: bool = False,
        next_retry_at: str | None = None,
        component_status: dict[str, Any] | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> dict[str, Any] | None:
        row = self.get_by_key(key)
        if not row:
            return None
        now = _utc_now()
        attempt = int(row["attempt_count"] or 0) + (1 if increment_attempt else 0)
        self._conn.execute(
            """
            UPDATE daily_fixture_drain SET
                queue_state=?,
                attempt_count=?,
                job_id=COALESCE(?, job_id),
                prediction_status=COALESCE(?, prediction_status),
                freeze_id=COALESCE(?, freeze_id),
                block_reason=COALESCE(?, block_reason),
                failure_code=COALESCE(?, failure_code),
                next_retry_at=?,
                component_status_json=COALESCE(?, component_status_json),
                started_at=CASE WHEN ? THEN COALESCE(started_at, ?) ELSE started_at END,
                finished_at=CASE WHEN ? THEN ? ELSE finished_at END,
                updated_at=?
            WHERE idempotency_key=?
            """,
            (
                queue_state,
                attempt,
                job_id,
                prediction_status,
                freeze_id,
                block_reason,
                failure_code,
                next_retry_at,
                json.dumps(component_status, ensure_ascii=False) if component_status is not None else None,
                1 if started else 0,
                now,
                1 if finished else 0,
                now,
                now,
                key,
            ),
        )
        self._conn.commit()
        return self.get_by_key(key)

    def reconcile(self, report_date: str) -> dict[str, int]:
        rows = self.list_for_date(report_date)
        counts: dict[str, int] = {"total": len(rows)}
        for r in rows:
            st = str(r["queue_state"])
            counts[st] = counts.get(st, 0) + 1
        pending = sum(1 for r in rows if r["queue_state"] in ACTIVE_STATES)
        terminal = sum(1 for r in rows if r["queue_state"] in TERMINAL_STATES)
        counts["pending"] = pending
        counts["terminal"] = terminal
        counts["queue_complete"] = int(pending == 0 and len(rows) > 0)
        return counts

    def export_day(self, report_date: str) -> list[dict[str, Any]]:
        return self.list_for_date(report_date)
