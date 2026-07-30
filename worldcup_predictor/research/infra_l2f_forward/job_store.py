"""Additive job-store upgrades for Phase 4 true-forward observability."""

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

_EXTRA_COLUMNS = (
    ("cohort_type", "TEXT"),
    ("classification", "TEXT"),
    ("kickoff_utc", "TEXT"),
    ("frozen_at_utc", "TEXT"),
    ("prediction_scope", "TEXT"),
    ("started_at_utc", "TEXT"),
    ("completed_at_utc", "TEXT"),
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def ensure_job_schema(conn: sqlite3.Connection) -> None:
    conn.execute(JOB_DDL)
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({JOB_TABLE})").fetchall()}
    for name, typ in _EXTRA_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE {JOB_TABLE} ADD COLUMN {name} {typ}")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_jobs_fx ON {JOB_TABLE}(fixture_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_jobs_status ON {JOB_TABLE}(status)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_jobs_cohort ON {JOB_TABLE}(cohort_type)")
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
    cohort_type: str | None = None,
    classification: str | None = None,
    kickoff_utc: str | None = None,
    frozen_at_utc: str | None = None,
    prediction_scope: str | None = None,
    started_at_utc: str | None = None,
    completed_at_utc: str | None = None,
) -> None:
    ensure_job_schema(conn)
    now = _now()
    conn.execute(
        f"""
        INSERT INTO {JOB_TABLE} (
            job_id, fixture_id, freeze_id, run_id, status, reason, retry_count,
            stages_json, lambda_rows, exact_rows, duration_ms, created_at_utc, updated_at_utc,
            cohort_type, classification, kickoff_utc, frozen_at_utc, prediction_scope,
            started_at_utc, completed_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(fixture_id, freeze_id, run_id) DO UPDATE SET
            status=excluded.status,
            reason=excluded.reason,
            retry_count=excluded.retry_count,
            stages_json=excluded.stages_json,
            lambda_rows=excluded.lambda_rows,
            exact_rows=excluded.exact_rows,
            duration_ms=excluded.duration_ms,
            updated_at_utc=excluded.updated_at_utc,
            cohort_type=COALESCE(excluded.cohort_type, {JOB_TABLE}.cohort_type),
            classification=COALESCE(excluded.classification, {JOB_TABLE}.classification),
            kickoff_utc=COALESCE(excluded.kickoff_utc, {JOB_TABLE}.kickoff_utc),
            frozen_at_utc=COALESCE(excluded.frozen_at_utc, {JOB_TABLE}.frozen_at_utc),
            prediction_scope=COALESCE(excluded.prediction_scope, {JOB_TABLE}.prediction_scope),
            started_at_utc=COALESCE(excluded.started_at_utc, {JOB_TABLE}.started_at_utc),
            completed_at_utc=COALESCE(excluded.completed_at_utc, {JOB_TABLE}.completed_at_utc)
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
            cohort_type,
            classification,
            kickoff_utc,
            frozen_at_utc,
            prediction_scope,
            started_at_utc,
            completed_at_utc,
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
