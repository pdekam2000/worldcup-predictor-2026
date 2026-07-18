"""Independent Challenger SQLite stores (additive; never touch WDE/ECSE tables)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.challenger.schemas import utc_now

CHALLENGER_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS challenger_predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        prediction_content_hash TEXT NOT NULL,
        feature_snapshot_hash TEXT,
        status TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        is_shadow INTEGER NOT NULL DEFAULT 1,
        is_user_visible INTEGER NOT NULL DEFAULT 0,
        final_decision_authority INTEGER NOT NULL DEFAULT 0,
        generated_at TEXT NOT NULL,
        UNIQUE(fixture_id, model_id, model_version, prediction_content_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS challenger_freezes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        linked_canonical_freeze_id TEXT,
        feature_snapshot_hash TEXT,
        prediction_content_hash TEXT NOT NULL,
        freeze_hash TEXT NOT NULL UNIQUE,
        payload_json TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        frozen_at TEXT NOT NULL,
        kickoff TEXT,
        immutable INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS challenger_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        freeze_hash TEXT,
        actuals_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        UNIQUE(fixture_id, model_id, model_version, freeze_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS challenger_comparisons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fixture_id INTEGER NOT NULL,
        model_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        canonical_freeze_hash TEXT,
        challenger_freeze_hash TEXT,
        conflict_class TEXT,
        comparison_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(fixture_id, model_id, model_version, challenger_freeze_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS challenger_model_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        model_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        phase TEXT NOT NULL,
        dataset_manifest_hash TEXT,
        metrics_json TEXT,
        artifact_meta_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS challenger_promotion_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_id TEXT NOT NULL,
        model_version TEXT NOT NULL,
        decision TEXT NOT NULL,
        evidence_hash TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_challenger_pred_fixture ON challenger_predictions(fixture_id)",
    "CREATE INDEX IF NOT EXISTS idx_challenger_freeze_fixture ON challenger_freezes(fixture_id)",
)


def ensure_challenger_schema(conn: sqlite3.Connection) -> None:
    for stmt in CHALLENGER_DDL:
        conn.execute(stmt)
    conn.commit()


def save_prediction(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    ensure_challenger_schema(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO challenger_predictions (
            fixture_id, model_id, model_version, prediction_content_hash, feature_snapshot_hash,
            status, payload_json, is_shadow, is_user_visible, final_decision_authority, generated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload["fixture_id"],
            payload["model_id"],
            payload["model_version"],
            payload["prediction_content_hash"],
            payload.get("feature_snapshot_hash"),
            payload.get("status"),
            json.dumps(payload, ensure_ascii=False, default=str),
            1 if payload.get("is_shadow", True) else 0,
            1 if payload.get("is_user_visible") else 0,
            1 if payload.get("final_decision_authority") else 0,
            payload.get("generated_at") or utc_now(),
        ),
    )
    conn.commit()


def save_freeze(
    conn: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    linked_canonical_freeze_id: str | None = None,
) -> dict[str, Any]:
    """Immutable: reuse first freeze for fixture+model+version."""
    ensure_challenger_schema(conn)
    existing = conn.execute(
        """
        SELECT id, freeze_hash, frozen_at, prediction_content_hash
        FROM challenger_freezes
        WHERE fixture_id=? AND model_id=? AND model_version=?
        ORDER BY id ASC LIMIT 1
        """,
        (payload["fixture_id"], payload["model_id"], payload["model_version"]),
    ).fetchone()
    if existing:
        return {
            "status": "reused",
            "freeze_id": existing["id"],
            "freeze_hash": existing["freeze_hash"],
            "frozen_at": existing["frozen_at"],
            "reused": True,
            "created": False,
        }
    from worldcup_predictor.challenger.schemas import content_hash

    frozen_at = utc_now()
    freeze_payload = {**payload, "frozen_at": frozen_at, "linked_canonical_freeze_id": linked_canonical_freeze_id}
    fh = content_hash(
        {
            "fixture_id": payload["fixture_id"],
            "model_id": payload["model_id"],
            "model_version": payload["model_version"],
            "prediction_content_hash": payload.get("prediction_content_hash"),
            "feature_snapshot_hash": payload.get("feature_snapshot_hash"),
            "frozen_at_bucket": "immutable_v1",
        }
    )
    cur = conn.execute(
        """
        INSERT INTO challenger_freezes (
            fixture_id, model_id, model_version, linked_canonical_freeze_id,
            feature_snapshot_hash, prediction_content_hash, freeze_hash,
            payload_json, generated_at, frozen_at, kickoff, immutable
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,1)
        """,
        (
            payload["fixture_id"],
            payload["model_id"],
            payload["model_version"],
            linked_canonical_freeze_id,
            payload.get("feature_snapshot_hash"),
            payload.get("prediction_content_hash"),
            fh,
            json.dumps(freeze_payload, ensure_ascii=False, default=str),
            payload.get("generated_at") or frozen_at,
            frozen_at,
            payload.get("kickoff"),
        ),
    )
    conn.commit()
    return {
        "status": "created",
        "freeze_id": cur.lastrowid,
        "freeze_hash": fh,
        "frozen_at": frozen_at,
        "reused": False,
        "created": True,
    }


def save_comparison(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    ensure_challenger_schema(conn)
    conn.execute(
        """
        INSERT OR IGNORE INTO challenger_comparisons (
            fixture_id, model_id, model_version, canonical_freeze_hash, challenger_freeze_hash,
            conflict_class, comparison_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            row["fixture_id"],
            row["model_id"],
            row["model_version"],
            row.get("canonical_freeze_hash"),
            row.get("challenger_freeze_hash"),
            row.get("conflict_class"),
            json.dumps(row, ensure_ascii=False, default=str),
            utc_now(),
        ),
    )
    conn.commit()


def save_model_run(conn: sqlite3.Connection, run: dict[str, Any]) -> None:
    ensure_challenger_schema(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO challenger_model_runs (
            run_id, model_id, model_version, phase, dataset_manifest_hash,
            metrics_json, artifact_meta_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            run["run_id"],
            run["model_id"],
            run["model_version"],
            run["phase"],
            run.get("dataset_manifest_hash"),
            json.dumps(run.get("metrics") or {}, ensure_ascii=False, default=str),
            json.dumps(run.get("artifact_meta") or {}, ensure_ascii=False, default=str),
            utc_now(),
        ),
    )
    conn.commit()


def save_promotion_review(conn: sqlite3.Connection, review: dict[str, Any]) -> None:
    ensure_challenger_schema(conn)
    conn.execute(
        """
        INSERT INTO challenger_promotion_reviews (
            model_id, model_version, decision, evidence_hash, evidence_json, created_at
        ) VALUES (?,?,?,?,?,?)
        """,
        (
            review["model_id"],
            review["model_version"],
            review["decision"],
            review["evidence_hash"],
            json.dumps(review, ensure_ascii=False, default=str),
            utc_now(),
        ),
    )
    conn.commit()
