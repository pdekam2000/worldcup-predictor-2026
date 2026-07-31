"""Research-only forward shadow store — separate from canonical freezes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.top10_to_5_optimizer.evidence import evidence_hash


SCHEMA = """
CREATE TABLE IF NOT EXISTS top10_to_5_forward_shadow (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fixture_id INTEGER NOT NULL,
  captured_at_utc TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  actual_score TEXT,
  evaluated_at_utc TEXT,
  net_pnl REAL,
  UNIQUE(fixture_id, evidence_hash)
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(SCHEMA)
    return conn


def persist_forward_shadow(
    recommendation: dict[str, Any],
    *,
    db_path: Path,
) -> dict[str, Any]:
    payload = dict(recommendation)
    payload["research_only"] = True
    payload["not_deployed"] = True
    payload["canonical_freeze_store"] = False
    h = evidence_hash(payload)
    fid = int(payload.get("fixture_id"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO top10_to_5_forward_shadow
            (fixture_id, captured_at_utc, payload_json, evidence_hash)
            VALUES (?, ?, ?, ?)
            """,
            (fid, now, json.dumps(payload, sort_keys=True), h),
        )
        conn.commit()
        cur = conn.execute(
            "SELECT COUNT(*) FROM top10_to_5_forward_shadow WHERE fixture_id=? AND evidence_hash=?",
            (fid, h),
        )
        n = int(cur.fetchone()[0])
    finally:
        conn.close()
    return {"fixture_id": fid, "evidence_hash": h, "persisted": n > 0, "idempotent": True, "db_path": str(db_path)}


def evaluate_forward_shadow(fixture_id: int, actual_score: str, *, db_path: Path, net_pnl: float | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE top10_to_5_forward_shadow
            SET actual_score=?, evaluated_at_utc=?, net_pnl=?
            WHERE fixture_id=? AND actual_score IS NULL
            """,
            (actual_score, now, net_pnl, int(fixture_id)),
        )
        conn.commit()
        cur = conn.execute("SELECT COUNT(*) FROM top10_to_5_forward_shadow WHERE fixture_id=?", (int(fixture_id),))
        n = int(cur.fetchone()[0])
    finally:
        conn.close()
    return {"fixture_id": fixture_id, "evaluated": True, "rows": n}


def summarize_forward_shadow(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"n": 0, "evaluated": 0, "research_only": True}
    conn = _connect(db_path)
    try:
        n = int(conn.execute("SELECT COUNT(*) FROM top10_to_5_forward_shadow").fetchone()[0])
        ev = int(conn.execute("SELECT COUNT(*) FROM top10_to_5_forward_shadow WHERE actual_score IS NOT NULL").fetchone()[0])
    finally:
        conn.close()
    return {
        "research_only": True,
        "not_deployed": True,
        "n_captured": n,
        "n_evaluated": ev,
        "db_path": str(db_path),
        "betting_execution": False,
        "production_activation": False,
    }
