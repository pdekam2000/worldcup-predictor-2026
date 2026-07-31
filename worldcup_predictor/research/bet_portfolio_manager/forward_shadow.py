"""Forward portfolio shadow store (research-only, no production execution)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DDL = """
CREATE TABLE IF NOT EXISTS portfolio_days (
  day_id TEXT PRIMARY KEY,
  prediction_date TEXT NOT NULL,
  stored_at_utc TEXT NOT NULL,
  score REAL,
  grade TEXT,
  action TEXT,
  payload_json TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def store_forward_day(db_path: Path, *, prediction_date: str, report: dict[str, Any]) -> str:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    day_id = f"pf_{prediction_date}"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(DDL)
        conn.execute(
            """
            INSERT OR REPLACE INTO portfolio_days(
              day_id, prediction_date, stored_at_utc, score, grade, action, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day_id,
                prediction_date,
                _utc_now(),
                float(report.get("daily_portfolio_score") or 0.0),
                str(report.get("grade") or ""),
                str(report.get("action") or ""),
                json.dumps(report),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return day_id


def summarize_forward(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"research_only": True, "n_days": 0, "days": []}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT prediction_date, score, grade, action FROM portfolio_days ORDER BY prediction_date"
        ).fetchall()
    finally:
        conn.close()
    grades: dict[str, int] = {}
    actions: dict[str, int] = {}
    for _, _, g, a in rows:
        grades[str(g)] = grades.get(str(g), 0) + 1
        actions[str(a)] = actions.get(str(a), 0) + 1
    return {
        "research_only": True,
        "no_production_execution": True,
        "n_days": len(rows),
        "grade_distribution": grades,
        "action_distribution": actions,
        "days": [
            {"date": d, "score": s, "grade": g, "action": a} for d, s, g, a in rows
        ],
    }
