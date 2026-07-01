"""Targeted DB helpers for owner predict/eval (no full-table scans)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import SOURCE_PROVIDER


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def latest_odds_snapshot(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return {
        "id": int(row["id"]),
        "snapshot_at": row["snapshot_at"],
        "payload": payload,
    }


def odds_source_label(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "none"
    for key in ("source_provider", "provider", "source", "api_call_source"):
        val = payload.get(key)
        if val:
            text = str(val).lower()
            if text == SOURCE_PROVIDER or "oddalerts_csv" in text:
                return "oddalerts_csv_policy"
            if text in ("api_football", "api-football", "sportmonks", "oddalerts", "the_odds_api"):
                return "provider"
            if text in ("live", "cache"):
                return "api"
            return text
    return "unknown"


def has_oddalerts_csv_policy_snapshot(conn: sqlite3.Connection, fixture_id: int) -> bool:
    snap = latest_odds_snapshot(conn, fixture_id)
    if not snap:
        return False
    payload = snap.get("payload") or {}
    if odds_source_label(payload) == "oddalerts_csv_policy":
        return True
    meta = payload.get("metadata") or {}
    return str(meta.get("source_provider") or "").lower() == SOURCE_PROVIDER


def has_wde_prediction(conn: sqlite3.Connection, fixture_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? AND payload_json IS NOT NULL LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return row is not None


def has_ecse_production_snapshot(conn: sqlite3.Connection, fixture_id: int) -> bool:
    if not table_exists(conn, "ecse_prediction_snapshots"):
        return False
    row = conn.execute(
        "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return row is not None


def has_ecse_oddalerts_shadow(conn: sqlite3.Connection, fixture_id: int) -> bool:
    if table_exists(conn, "ecse_oddalerts_shadow_predictions"):
        row = conn.execute(
            "SELECT 1 FROM ecse_oddalerts_shadow_predictions WHERE fixture_id=? LIMIT 1",
            (int(fixture_id),),
        ).fetchone()
        if row:
            return True
    if table_exists(conn, "ecse_oddalerts_shadow_monitor"):
        row = conn.execute(
            "SELECT 1 FROM ecse_oddalerts_shadow_monitor WHERE fixture_id=? LIMIT 1",
            (int(fixture_id),),
        ).fetchone()
        if row:
            return True
    return False


def has_fixture_result(conn: sqlite3.Connection, fixture_id: int) -> bool:
    if not table_exists(conn, "fixture_results"):
        return False
    row = conn.execute(
        "SELECT 1 FROM fixture_results WHERE fixture_id=? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return row is not None


def load_fixture_result(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    if not table_exists(conn, "fixture_results"):
        return None
    row = conn.execute(
        "SELECT * FROM fixture_results WHERE fixture_id=? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return dict(row) if row else None
