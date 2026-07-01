"""PHASE ECSE-LIVE-1 — Immutable ECSE snapshot / evaluation store."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL

PHASE = "ECSE-LIVE-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_ecse_live_tables(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    conn.commit()


def has_snapshot(conn: sqlite3.Connection, fixture_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id = ? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    return row is not None


def get_snapshot(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id = ?",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    return _hydrate_snapshot(dict(row))


def get_snapshot_by_id(conn: sqlite3.Connection, snapshot_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE id = ?",
        (int(snapshot_id),),
    ).fetchone()
    if not row:
        return None
    return _hydrate_snapshot(dict(row))


def _hydrate_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    for key in ("top_10_scorelines_json", "top_3_scores_json", "top_5_scores_json", "raw_features_json"):
        raw = item.get(key)
        if isinstance(raw, str):
            try:
                item[key.replace("_json", "") if key.endswith("_json") else key] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    if "top_10_scorelines_json" in item and isinstance(item["top_10_scorelines_json"], str):
        try:
            item["top_10_scorelines"] = json.loads(item["top_10_scorelines_json"])
        except json.JSONDecodeError:
            item["top_10_scorelines"] = []
    if "top_3_scores_json" in item and isinstance(item["top_3_scores_json"], str):
        try:
            item["top_3_scores"] = json.loads(item["top_3_scores_json"])
        except json.JSONDecodeError:
            item["top_3_scores"] = []
    if "top_5_scores_json" in item and isinstance(item["top_5_scores_json"], str):
        try:
            item["top_5_scores"] = json.loads(item["top_5_scores_json"])
        except json.JSONDecodeError:
            item["top_5_scores"] = []
    if "raw_features_json" in item and isinstance(item["raw_features_json"], str):
        try:
            item["raw_features"] = json.loads(item["raw_features_json"])
        except json.JSONDecodeError:
            item["raw_features"] = {}
    return item


def insert_snapshot(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[int | None, str]:
    """Insert frozen snapshot once per fixture_id. Never overwrites."""
    fixture_id = int(payload["fixture_id"])
    if has_snapshot(conn, fixture_id):
        return None, "already_exists"

    snapshot_key = f"ecse-live:{fixture_id}"
    top_10 = payload["top_10_scorelines"]
    top_3 = payload["top_3_scores"]
    top_5 = payload["top_5_scores"]
    try:
        cur = conn.execute(
            """
            INSERT INTO ecse_prediction_snapshots (
                snapshot_key, fixture_id, registry_fixture_id, competition_key,
                home_team, away_team, kickoff_utc, generated_at, model_version,
                lambda_home, lambda_away, top_10_scorelines_json,
                top_1_score, top_3_scores_json, top_5_scores_json,
                confidence_score, data_quality_score, raw_features_json,
                prediction_source, is_frozen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                snapshot_key,
                fixture_id,
                payload.get("registry_fixture_id"),
                payload.get("competition_key"),
                payload.get("home_team"),
                payload.get("away_team"),
                payload.get("kickoff_utc"),
                payload.get("generated_at") or _utc_now(),
                payload["model_version"],
                float(payload["lambda_home"]),
                float(payload["lambda_away"]),
                json.dumps(top_10, default=str),
                payload["top_1_score"],
                json.dumps(top_3, default=str),
                json.dumps(top_5, default=str),
                float(payload["confidence_score"]),
                float(payload["data_quality_score"]),
                json.dumps(payload.get("raw_features") or {}, default=str),
                payload.get("prediction_source") or "live_odds",
            ),
        )
        conn.commit()
        return int(cur.lastrowid), "inserted"
    except sqlite3.IntegrityError:
        conn.rollback()
        return None, "duplicate"


def has_evaluation(conn: sqlite3.Connection, snapshot_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ecse_prediction_evaluations WHERE snapshot_id = ? LIMIT 1",
        (int(snapshot_id),),
    ).fetchone()
    return row is not None


def list_snapshots_needing_evaluation(conn: sqlite3.Connection, *, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.*
        FROM ecse_prediction_snapshots s
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        WHERE e.id IS NULL
        ORDER BY s.kickoff_utc ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [_hydrate_snapshot(dict(r)) for r in rows]


def insert_evaluation(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[int | None, str]:
    snapshot_id = int(payload["snapshot_id"])
    if has_evaluation(conn, snapshot_id):
        return None, "already_exists"
    try:
        cur = conn.execute(
            """
            INSERT INTO ecse_prediction_evaluations (
                snapshot_id, fixture_id, final_score,
                top1_correct, top3_correct, top5_correct, top10_correct,
                rank_of_actual_score, actual_home_goals, actual_away_goals,
                status, evaluated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                int(payload["fixture_id"]),
                payload.get("final_score"),
                1 if payload.get("top1_correct") else 0,
                1 if payload.get("top3_correct") else 0,
                1 if payload.get("top5_correct") else 0,
                1 if payload.get("top10_correct") else 0,
                payload.get("rank_of_actual_score"),
                payload.get("actual_home_goals"),
                payload.get("actual_away_goals"),
                payload.get("status") or "evaluated",
                payload.get("evaluated_at") or _utc_now(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid), "inserted"
    except sqlite3.IntegrityError:
        conn.rollback()
        return None, "duplicate"
