"""Challenger evaluation store helpers."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.challenger.prediction_store import ensure_challenger_schema
from worldcup_predictor.challenger.schemas import utc_now


def save_evaluation(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    ensure_challenger_schema(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO challenger_evaluations (
            fixture_id, model_id, model_version, freeze_hash, actuals_json, metrics_json, evaluated_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            row["fixture_id"],
            row["model_id"],
            row["model_version"],
            row.get("freeze_hash"),
            json.dumps(row.get("actuals") or {}, ensure_ascii=False, default=str),
            json.dumps(row.get("metrics") or {}, ensure_ascii=False, default=str),
            utc_now(),
        ),
    )
    conn.commit()
