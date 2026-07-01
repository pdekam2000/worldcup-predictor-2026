"""PHASE SAFE-BETS-1 — Candidate storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.safe_bets.ddl import PHASE_SAFE_BETS_DDL

PHASE = "SAFE-BETS-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_safe_bets_tables(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_SAFE_BETS_DDL:
        conn.execute(ddl)
    conn.commit()


def candidate_key(
    *,
    fixture_id: int,
    provider: str,
    bookmaker: str,
    market: str,
    selection: str,
) -> str:
    raw = f"{fixture_id}|{provider}|{bookmaker}|{market}|{selection}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def log_api_call(
    conn: sqlite3.Connection,
    *,
    scan_batch_id: str,
    provider: str,
    endpoint: str,
    entity_key: str | None,
    action: str,
    status: str,
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO safe_bets_api_log (
            scan_batch_id, provider, endpoint, entity_key, action, status, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_batch_id,
            provider,
            endpoint,
            entity_key,
            action,
            status,
            json.dumps(details or {}, default=str),
            _utc_now(),
        ),
    )


def insert_candidate(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[bool, str]:
    key = payload["candidate_key"]
    try:
        conn.execute(
            """
            INSERT INTO safe_bet_candidates (
                candidate_key, scan_batch_id, fixture_id, match_name, kickoff_utc,
                market, market_type, selection, odds, implied_probability,
                devigged_probability, probability_bucket, usefulness_score,
                trap_flag, reason, provider, bookmaker, data_quality, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                payload["scan_batch_id"],
                int(payload["fixture_id"]),
                payload.get("match_name"),
                payload.get("kickoff_utc"),
                payload["market"],
                payload.get("market_type"),
                payload["selection"],
                float(payload["odds"]),
                float(payload["implied_probability"]),
                payload.get("devigged_probability"),
                payload.get("probability_bucket"),
                float(payload["usefulness_score"]),
                1 if payload.get("trap_flag") else 0,
                payload.get("reason"),
                payload["provider"],
                payload.get("bookmaker"),
                payload.get("data_quality"),
                payload.get("created_at") or _utc_now(),
            ),
        )
        return True, "inserted"
    except sqlite3.IntegrityError:
        return False, "duplicate"


def start_scan_run(conn: sqlite3.Connection, scan_batch_id: str, *, hours_window: int) -> None:
    conn.execute(
        """
        INSERT INTO safe_bets_scan_runs (scan_batch_id, started_at, status, hours_window)
        VALUES (?, ?, 'running', ?)
        """,
        (scan_batch_id, _utc_now(), int(hours_window)),
    )
    conn.commit()


def finish_scan_run(conn: sqlite3.Connection, scan_batch_id: str, report: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE safe_bets_scan_runs
        SET finished_at = ?, status = ?, fixtures_scanned = ?, candidates_stored = ?,
            traps_flagged = ?, api_calls = ?, report_json = ?
        WHERE scan_batch_id = ?
        """,
        (
            _utc_now(),
            report.get("status", "ok"),
            report.get("fixtures_scanned", 0),
            report.get("candidates_stored", 0),
            report.get("traps_flagged", 0),
            report.get("api_calls", 0),
            json.dumps(report, default=str),
            scan_batch_id,
        ),
    )
    conn.commit()
