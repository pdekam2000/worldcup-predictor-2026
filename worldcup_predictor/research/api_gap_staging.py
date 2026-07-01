"""PHASE API-GAP-1 — Staging tables for targeted harvest (research only)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

PHASE = "API-GAP-1"

DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS api_gap_harvest_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phase TEXT NOT NULL,
        provider TEXT NOT NULL,
        data_type TEXT NOT NULL,
        entity_key TEXT NOT NULL,
        action TEXT NOT NULL,
        details_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_gap_harvest_log_provider
    ON api_gap_harvest_log(provider, data_type, created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS api_gap_raw_payload (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        entity_key TEXT NOT NULL,
        data_type TEXT NOT NULL,
        registry_fixture_id INTEGER,
        fixture_id INTEGER,
        payload_json TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(provider, entity_key, data_type)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_gap_raw_registry
    ON api_gap_raw_payload(registry_fixture_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_api_gap_raw_fixture
    ON api_gap_raw_payload(fixture_id)
    """,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_api_gap_tables(conn: sqlite3.Connection) -> None:
    for ddl in DDL:
        conn.execute(ddl)
    conn.commit()


def log_harvest(
    conn: sqlite3.Connection,
    *,
    provider: str,
    data_type: str,
    entity_key: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO api_gap_harvest_log (phase, provider, data_type, entity_key, action, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (PHASE, provider, data_type, entity_key, action, json.dumps(details or {}), _utc_now()),
    )


def upsert_raw_payload(
    conn: sqlite3.Connection,
    *,
    provider: str,
    entity_key: str,
    data_type: str,
    payload: dict[str, Any] | list[Any],
    source: str,
    registry_fixture_id: int | None = None,
    fixture_id: int | None = None,
    dry_run: bool = False,
) -> bool:
    if dry_run:
        return True
    try:
        conn.execute(
            """
            INSERT INTO api_gap_raw_payload (
                provider, entity_key, data_type, registry_fixture_id, fixture_id,
                payload_json, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, entity_key, data_type) DO NOTHING
            """,
            (
                provider,
                entity_key,
                data_type,
                registry_fixture_id,
                fixture_id,
                json.dumps(payload, ensure_ascii=False, default=str),
                source,
                _utc_now(),
            ),
        )
        return conn.total_changes > 0
    except sqlite3.Error:
        return False


def harvest_log_summary(conn: sqlite3.Connection, *, provider: str | None = None) -> dict[str, Any]:
    where = "WHERE phase = ?"
    params: list[Any] = [PHASE]
    if provider:
        where += " AND provider = ?"
        params.append(provider)
    rows = conn.execute(
        f"""
        SELECT provider, data_type, action, COUNT(1) AS n
        FROM api_gap_harvest_log
        {where}
        GROUP BY provider, data_type, action
        ORDER BY provider, data_type, action
        """,
        params,
    ).fetchall()
    return {"by_action": [dict(r) for r in rows]}
