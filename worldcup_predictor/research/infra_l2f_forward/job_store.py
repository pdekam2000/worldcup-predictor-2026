"""Persistent job status for L2-F forward shadow (additive; never touches freezes)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

JOB_TABLE = "l2f_forward_shadow_jobs"

JOB_DDL = f"""
CREATE TABLE IF NOT EXISTS {JOB_TABLE} (
    job_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    freeze_id TEXT,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    stages_json TEXT,
    lambda_rows INTEGER,
    exact_rows INTEGER,
    duration_ms REAL,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(fixture_id, freeze_id, run_id)
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def ensure_job_schema(conn: sqlite3.Connection) -> None:
    conn.execute(JOB_DDL)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_jobs_fx ON {JOB_TABLE}(fixture_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_jobs_status ON {JOB_TABLE}(status)")
    conn.commit()


def upsert_job(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    fixture_id: int,
    freeze_id: str | None,
    run_id: str,
    status: str,
    reason: str | None = None,
    retry_count: int = 0,
    stages: list[dict[str, Any]] | None = None,
    lambda_rows: int = 0,
    exact_rows: int = 0,
    duration_ms: float | None = None,
) -> None:
    ensure_job_schema(conn)
    now = _now()
    conn.execute(
        f"""
        INSERT INTO {JOB_TABLE} (
            job_id, fixture_id, freeze_id, run_id, status, reason, retry_count,
            stages_json, lambda_rows, exact_rows, duration_ms, created_at_utc, updated_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(fixture_id, freeze_id, run_id) DO UPDATE SET
            status=excluded.status,
            reason=excluded.reason,
            retry_count=excluded.retry_count,
            stages_json=excluded.stages_json,
            lambda_rows=excluded.lambda_rows,
            exact_rows=excluded.exact_rows,
            duration_ms=excluded.duration_ms,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            job_id,
            int(fixture_id),
            freeze_id,
            run_id,
            status,
            reason,
            int(retry_count),
            json.dumps(stages or [], default=str),
            int(lambda_rows),
            int(exact_rows),
            duration_ms,
            now,
            now,
        ),
    )
    conn.commit()


def get_job(conn: sqlite3.Connection, *, fixture_id: int, freeze_id: str | None, run_id: str) -> dict[str, Any] | None:
    ensure_job_schema(conn)
    row = conn.execute(
        f"""
        SELECT * FROM {JOB_TABLE}
        WHERE fixture_id=? AND IFNULL(freeze_id,'')=IFNULL(?, '') AND run_id=?
        """,
        (int(fixture_id), freeze_id, run_id),
    ).fetchone()
    if not row:
        return None
    return dict(row)
