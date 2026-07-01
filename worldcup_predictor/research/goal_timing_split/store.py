"""PHASE GT-1 — Prediction storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.goal_timing_split.ddl import PHASE_GOAL_TIMING_SPLIT_DDL

PHASE = "GT-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_goal_timing_split_tables(conn: sqlite3.Connection) -> None:
    for ddl in PHASE_GOAL_TIMING_SPLIT_DDL:
        conn.execute(ddl)
    conn.commit()


def prediction_key(*, fixture_id: int, model_version: str) -> str:
    raw = f"{fixture_id}|{model_version}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def has_prediction(conn: sqlite3.Connection, fixture_id: int, model_version: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM goal_timing_split_predictions
        WHERE fixture_id = ? AND model_version = ?
        LIMIT 1
        """,
        (int(fixture_id), model_version),
    ).fetchone()
    return row is not None


def insert_prediction(conn: sqlite3.Connection, payload: dict[str, Any]) -> tuple[bool, str]:
    key = prediction_key(
        fixture_id=int(payload["fixture_id"]),
        model_version=str(payload["model_version"]),
    )
    if has_prediction(conn, int(payload["fixture_id"]), str(payload["model_version"])):
        return False, "already_exists"
    try:
        conn.execute(
            """
            INSERT INTO goal_timing_split_predictions (
                prediction_key, fixture_id, match_name, kickoff_utc,
                home_team, away_team,
                p_home_0_30, p_away_0_30, p_home_31_plus, p_away_31_plus, p_no_goal,
                recommended_side, recommended_window, confidence_tier,
                data_quality_score, raw_features_json, created_at, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                int(payload["fixture_id"]),
                payload.get("match_name"),
                payload.get("kickoff_utc"),
                payload["home_team"],
                payload["away_team"],
                payload.get("p_home_0_30"),
                payload.get("p_away_0_30"),
                payload.get("p_home_31_plus"),
                payload.get("p_away_31_plus"),
                payload.get("p_no_goal"),
                payload["recommended_side"],
                payload["recommended_window"],
                payload["confidence_tier"],
                payload.get("data_quality_score"),
                json.dumps(payload.get("raw_features") or {}, default=str),
                payload.get("created_at") or _utc_now(),
                payload["model_version"],
            ),
        )
        return True, "inserted"
    except sqlite3.IntegrityError:
        return False, "duplicate"


def get_prediction(conn: sqlite3.Connection, fixture_id: int, model_version: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM goal_timing_split_predictions
        WHERE fixture_id = ? AND model_version = ?
        """,
        (int(fixture_id), model_version),
    ).fetchone()
    return dict(row) if row else None
