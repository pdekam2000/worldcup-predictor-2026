"""PredOps SQLite store — Phase A15."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.predops.constants import (
    QUEUE_STATUS_COMPLETED,
    QUEUE_STATUS_FAILED,
    QUEUE_STATUS_GENERATING,
    QUEUE_STATUS_QUEUED,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _job_key(fixture_id: int, competition_key: str) -> str:
    return f"{int(fixture_id)}:{competition_key}"


class PredOpsStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._conn = self._repo._conn  # noqa: SLF001
        ensure_schema_compat(self._conn)

    # --- Queue ---

    def enqueue_job(
        self,
        *,
        fixture_id: int,
        competition_key: str,
        kickoff_utc: str | None,
        priority_band: int,
        trigger_reason: str,
        max_attempts: int = 3,
    ) -> tuple[bool, str]:
        key = _job_key(fixture_id, competition_key)
        now = _utc_now()
        existing = self._conn.execute(
            "SELECT status FROM predops_queue WHERE job_key = ?",
            (key,),
        ).fetchone()
        if existing:
            status = str(existing[0])
            if status in (QUEUE_STATUS_QUEUED, QUEUE_STATUS_GENERATING):
                return False, "duplicate_active"
            if status == QUEUE_STATUS_COMPLETED:
                self._conn.execute(
                    """
                    UPDATE predops_queue
                    SET status = ?, priority_band = ?, trigger_reason = ?, updated_at = ?,
                        attempts = 0, failure_reason = NULL, next_retry_at = NULL,
                        started_at = NULL, finished_at = NULL
                    WHERE job_key = ?
                    """,
                    (QUEUE_STATUS_QUEUED, priority_band, trigger_reason, now, key),
                )
                self._conn.commit()
                return True, "requeued_completed"
            return False, f"exists_{status}"

        self._conn.execute(
            """
            INSERT INTO predops_queue (
                job_key, fixture_id, competition_key, kickoff_utc, priority_band,
                status, attempts, max_attempts, trigger_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                key,
                int(fixture_id),
                competition_key,
                kickoff_utc,
                int(priority_band),
                QUEUE_STATUS_QUEUED,
                int(max_attempts),
                trigger_reason,
                now,
                now,
            ),
        )
        self._conn.commit()
        return True, "inserted"

    def claim_next_jobs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        now = _utc_now()
        rows = self._conn.execute(
            """
            SELECT * FROM predops_queue
            WHERE status = ?
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
            ORDER BY priority_band ASC, kickoff_utc ASC
            LIMIT ?
            """,
            (QUEUE_STATUS_QUEUED, now, int(limit)),
        ).fetchall()
        claimed: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            self._conn.execute(
                """
                UPDATE predops_queue
                SET status = ?, started_at = ?, updated_at = ?, attempts = attempts + 1
                WHERE id = ? AND status = ?
                """,
                (QUEUE_STATUS_GENERATING, now, now, d["id"], QUEUE_STATUS_QUEUED),
            )
            if self._conn.total_changes:
                d["status"] = QUEUE_STATUS_GENERATING
                claimed.append(d)
        self._conn.commit()
        return claimed

    def complete_job(self, job_id: int) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            UPDATE predops_queue
            SET status = ?, finished_at = ?, updated_at = ?, failure_reason = NULL
            WHERE id = ?
            """,
            (QUEUE_STATUS_COMPLETED, now, now, int(job_id)),
        )
        self._conn.commit()

    def fail_job(self, job_id: int, *, reason: str, backoff_minutes: int = 30) -> None:
        now = _utc_now()
        row = self._conn.execute(
            "SELECT attempts, max_attempts FROM predops_queue WHERE id = ?",
            (int(job_id),),
        ).fetchone()
        if not row:
            return
        attempts, max_attempts = int(row[0]), int(row[1])
        if attempts >= max_attempts:
            status = QUEUE_STATUS_FAILED
            next_retry = None
        else:
            status = QUEUE_STATUS_QUEUED
            next_retry = (
                datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=backoff_minutes)
            ).isoformat()
        self._conn.execute(
            """
            UPDATE predops_queue
            SET status = ?, failure_reason = ?, updated_at = ?, finished_at = ?, next_retry_at = ?
            WHERE id = ?
            """,
            (status, reason[:500], now, now if status == QUEUE_STATUS_FAILED else None, next_retry, int(job_id)),
        )
        self._conn.commit()

    def queue_stats(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS c FROM predops_queue GROUP BY status"
        ).fetchall()
        out = {str(r[0]): int(r[1]) for r in rows}
        out["total"] = sum(out.values())
        return out

    def list_queue(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM predops_queue WHERE status = ? ORDER BY priority_band, kickoff_utc LIMIT ?",
                (status, int(limit)),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM predops_queue ORDER BY priority_band, kickoff_utc LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def fixture_queue_state(self, fixture_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM predops_queue WHERE fixture_id = ? ORDER BY updated_at DESC LIMIT 1",
            (int(fixture_id),),
        ).fetchone()
        return str(row[0]) if row else None

    # --- Snapshots ---

    def insert_snapshot(
        self,
        *,
        fixture_id: int,
        competition_key: str,
        kickoff_utc: str | None,
        trigger_reason: str,
        payload: dict[str, Any],
        markets: dict[str, Any],
        egie: dict[str, Any] | None,
        deltas: dict[str, Any] | None,
        coverage_state: str,
        engine_version: str | None,
        previous_snapshot_id: str | None,
    ) -> str:
        snapshot_id = str(uuid.uuid4())
        now = _utc_now()
        self._conn.execute(
            "UPDATE predops_snapshots SET is_latest = 0 WHERE fixture_id = ? AND is_latest = 1",
            (int(fixture_id),),
        )
        self._conn.execute(
            """
            INSERT INTO predops_snapshots (
                snapshot_id, fixture_id, competition_key, kickoff_utc, generated_at,
                trigger_reason, previous_snapshot_id, payload_json, markets_json,
                egie_json, deltas_json, coverage_state, engine_version, is_latest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                snapshot_id,
                int(fixture_id),
                competition_key,
                kickoff_utc,
                now,
                trigger_reason,
                previous_snapshot_id,
                json.dumps(payload, default=str),
                json.dumps(markets, default=str),
                json.dumps(egie or {}, default=str),
                json.dumps(deltas or {}, default=str),
                coverage_state,
                engine_version,
            ),
        )
        self._conn.commit()
        return snapshot_id

    def get_latest_snapshot(self, fixture_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT * FROM predops_snapshots
            WHERE fixture_id = ? AND is_latest = 1
            ORDER BY generated_at DESC LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def list_snapshot_history(self, fixture_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM predops_snapshots
            WHERE fixture_id = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (int(fixture_id), int(limit)),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def count_latest_snapshots(self, competition_key: str | None = None) -> int:
        if competition_key:
            row = self._conn.execute(
                """
                SELECT COUNT(*) FROM predops_snapshots
                WHERE is_latest = 1 AND competition_key = ?
                """,
                (competition_key,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM predops_snapshots WHERE is_latest = 1",
            ).fetchone()
        return int(row[0]) if row else 0

    def latest_by_fixtures(self, fixture_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not fixture_ids:
            return {}
        placeholders = ",".join("?" for _ in fixture_ids)
        rows = self._conn.execute(
            f"""
            SELECT * FROM predops_snapshots
            WHERE fixture_id IN ({placeholders}) AND is_latest = 1
            """,
            [int(x) for x in fixture_ids],
        ).fetchall()
        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            snap = self._row_to_snapshot(row)
            out[int(snap["fixture_id"])] = snap
        return out

    def _row_to_snapshot(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("payload_json", "markets_json", "egie_json", "deltas_json"):
            raw = d.pop(key, None)
            if isinstance(raw, str) and raw.strip():
                try:
                    d[key.replace("_json", "")] = json.loads(raw)
                except json.JSONDecodeError:
                    d[key.replace("_json", "")] = {}
            elif isinstance(raw, dict):
                d[key.replace("_json", "")] = raw
            else:
                d[key.replace("_json", "")] = {}
        return d

    def save_scheduler_run(self, report: dict[str, Any], *, status: str = "ok") -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO predops_scheduler_runs (started_at, finished_at, status, report_json)
            VALUES (?, ?, ?, ?)
            """,
            (report.get("started_at", now), now, status, json.dumps(report, default=str)),
        )
        self._conn.commit()

    def last_scheduler_run(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM predops_scheduler_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["report"] = json.loads(d.pop("report_json", "{}") or "{}")
        except json.JSONDecodeError:
            d["report"] = {}
        return d
