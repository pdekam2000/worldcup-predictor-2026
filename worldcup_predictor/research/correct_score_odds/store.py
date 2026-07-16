"""Append-only store for Correct Score odds lines."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.research.correct_score_odds.ddl import ensure_correct_score_odds_schema

INSERT_SQL = """
INSERT OR IGNORE INTO correct_score_odds_lines (
    fixture_id, provider_fixture_id, bookmaker_id, bookmaker_name, market, selection,
    home_goals, away_goals, decimal_odds, raw_odds_format, fetched_at_utc, valid_from_utc,
    kickoff_utc, prematch_status, settlement_scope, provider, source_hash, payload_reference,
    snapshot_id, is_complete_market, is_fresh, odds_age_seconds, currency, minimum_stake,
    maximum_stake, market_status, ingestion_run_id, odds_kind, created_at_utc
) VALUES (
    :fixture_id, :provider_fixture_id, :bookmaker_id, :bookmaker_name, :market, :selection,
    :home_goals, :away_goals, :decimal_odds, :raw_odds_format, :fetched_at_utc, :valid_from_utc,
    :kickoff_utc, :prematch_status, :settlement_scope, :provider, :source_hash, :payload_reference,
    :snapshot_id, :is_complete_market, :is_fresh, :odds_age_seconds, :currency, :minimum_stake,
    :maximum_stake, :market_status, :ingestion_run_id, :odds_kind, :created_at_utc
)
"""


def insert_lines(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert rows; returns (inserted, deduped)."""
    ensure_correct_score_odds_schema(conn)
    inserted = 0
    deduped = 0
    for row in rows:
        before = conn.total_changes
        conn.execute(INSERT_SQL, row)
        if conn.total_changes > before:
            inserted += 1
        else:
            deduped += 1
    conn.commit()
    return inserted, deduped


def start_run(conn: sqlite3.Connection, run_id: str, mode: str, started: str) -> None:
    ensure_correct_score_odds_schema(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO correct_score_odds_ingestion_runs (
            ingestion_run_id, started_at_utc, mode, status
        ) VALUES (?, ?, ?, 'running')
        """,
        (run_id, started, mode),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    finished: str,
    fixtures_scanned: int,
    lines_inserted: int,
    lines_rejected: int,
    lines_deduped: int,
    status: str,
    notes: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        UPDATE correct_score_odds_ingestion_runs
        SET finished_at_utc=?, fixtures_scanned=?, lines_inserted=?, lines_rejected=?,
            lines_deduped=?, status=?, notes_json=?
        WHERE ingestion_run_id=?
        """,
        (
            finished,
            fixtures_scanned,
            lines_inserted,
            lines_rejected,
            lines_deduped,
            status,
            json.dumps(notes or {}),
            run_id,
        ),
    )
    conn.commit()


def best_odds_map(
    conn: sqlite3.Connection,
    fixture_id: int,
    *,
    prematch_only: bool = True,
) -> dict[str, dict[str, Any]]:
    """Best decimal odds per exact-score selection across bookmakers."""
    ensure_correct_score_odds_schema(conn)
    q = """
    SELECT selection, bookmaker_name, decimal_odds, provider, fetched_at_utc, market
    FROM correct_score_odds_lines
    WHERE fixture_id = ?
      AND market = 'CORRECT_SCORE_90_MINUTES'
      AND decimal_odds > 1
    """
    if prematch_only:
        q += " AND prematch_status = 'prematch'"
    q += " ORDER BY decimal_odds DESC"
    out: dict[str, dict[str, Any]] = {}
    for r in conn.execute(q, (fixture_id,)):
        sel = str(r["selection"])
        if sel not in out:
            out[sel] = dict(r)
    return out


def single_bookmaker_maps(
    conn: sqlite3.Connection,
    fixture_id: int,
) -> dict[str, dict[str, float]]:
    ensure_correct_score_odds_schema(conn)
    maps: dict[str, dict[str, float]] = {}
    for r in conn.execute(
        """
        SELECT bookmaker_name, selection, MAX(decimal_odds) AS odd
        FROM correct_score_odds_lines
        WHERE fixture_id = ?
          AND market = 'CORRECT_SCORE_90_MINUTES'
          AND prematch_status = 'prematch'
        GROUP BY bookmaker_name, selection
        """,
        (fixture_id,),
    ):
        bm = str(r["bookmaker_name"])
        maps.setdefault(bm, {})[str(r["selection"])] = float(r["odd"])
    return maps


def fixture_status(conn: sqlite3.Connection, fixture_id: int, required_scores: list[str]) -> str:
    from worldcup_predictor.research.correct_score_odds.statuses import (
        CS_ODDS_AVAILABLE,
        CS_ODDS_PARTIAL,
        CS_ODDS_UNAVAILABLE,
    )

    m = best_odds_map(conn, fixture_id)
    if not m:
        return CS_ODDS_UNAVAILABLE
    have = sum(1 for s in required_scores if s in m)
    if have == 0:
        return CS_ODDS_UNAVAILABLE
    if have < len(required_scores):
        return CS_ODDS_PARTIAL
    return CS_ODDS_AVAILABLE
