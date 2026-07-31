"""Forward-shadow store + evaluation (research-only SQLite)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DDL = """
CREATE TABLE IF NOT EXISTS prediction_days (
  day_id TEXT PRIMARY KEY,
  prediction_date TEXT NOT NULL,
  stored_at_utc TEXT NOT NULL,
  budget_json TEXT,
  coverage_report_json TEXT,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_id TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  layer TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  UNIQUE(day_id, ticket_id)
);

CREATE TABLE IF NOT EXISTS evaluations (
  day_id TEXT PRIMARY KEY,
  evaluated_at_utc TEXT NOT NULL,
  main_only_json TEXT,
  main_plus_insurance_json TEXT,
  insurance_hit_rate REAL,
  coverage_gain REAL,
  daily_roi REAL,
  notes TEXT
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(DDL)
    return conn


def store_prediction_day(
    db_path: Path,
    *,
    prediction_date: str,
    main_tickets: list[dict[str, Any]],
    insurance_tickets: list[dict[str, Any]],
    coverage_report: dict[str, Any],
    budget: dict[str, Any],
    day_id: str | None = None,
) -> str:
    did = day_id or f"day_{prediction_date}"
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO prediction_days(day_id, prediction_date, stored_at_utc, budget_json, coverage_report_json, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                prediction_date,
                _utc_now(),
                json.dumps(budget),
                json.dumps(coverage_report),
                "STORED",
            ),
        )
        conn.execute("DELETE FROM tickets WHERE day_id = ?", (did,))
        for t in main_tickets:
            tid = str(t.get("ticket_id") or t.get("ticket_number") or "")
            conn.execute(
                "INSERT INTO tickets(day_id, ticket_id, layer, payload_json) VALUES (?, ?, ?, ?)",
                (did, tid, "main", json.dumps(t)),
            )
        for t in insurance_tickets:
            tid = str(t.get("ticket_id") or "")
            conn.execute(
                "INSERT INTO tickets(day_id, ticket_id, layer, payload_json) VALUES (?, ?, ?, ?)",
                (did, tid, "insurance", json.dumps(t)),
            )
        conn.commit()
    finally:
        conn.close()
    return did


def evaluate_prediction_day(
    db_path: Path,
    *,
    day_id: str,
    main_only_result: dict[str, Any],
    main_plus_insurance_result: dict[str, Any],
    insurance_hit_rate: float | None,
    coverage_gain: float | None,
    daily_roi: float | None,
    notes: str | None = None,
) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO evaluations(
              day_id, evaluated_at_utc, main_only_json, main_plus_insurance_json,
              insurance_hit_rate, coverage_gain, daily_roi, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day_id,
                _utc_now(),
                json.dumps(main_only_result),
                json.dumps(main_plus_insurance_result),
                insurance_hit_rate,
                coverage_gain,
                daily_roi,
                notes,
            ),
        )
        conn.execute("UPDATE prediction_days SET status = ? WHERE day_id = ?", ("EVALUATED", day_id))
        conn.commit()
    finally:
        conn.close()


def summarize_forward_shadow(db_path: Path) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        days = conn.execute("SELECT day_id, prediction_date, status FROM prediction_days ORDER BY prediction_date").fetchall()
        evals = conn.execute(
            "SELECT day_id, insurance_hit_rate, coverage_gain, daily_roi, evaluated_at_utc FROM evaluations"
        ).fetchall()
        ticket_counts = conn.execute(
            "SELECT layer, COUNT(*) FROM tickets GROUP BY layer"
        ).fetchall()
    finally:
        conn.close()

    daily_rois = [float(r[3]) for r in evals if r[3] is not None]
    weekly_roi = round(sum(daily_rois[-7:]), 8) if daily_rois else None
    monthly_roi = round(sum(daily_rois[-30:]), 8) if daily_rois else None
    hit_rates = [float(r[1]) for r in evals if r[1] is not None]
    gains = [float(r[2]) for r in evals if r[2] is not None]

    return {
        "research_only": True,
        "owner_only": True,
        "db_path": str(db_path),
        "n_prediction_days": len(days),
        "n_evaluations": len(evals),
        "ticket_counts_by_layer": {str(k): int(v) for k, v in ticket_counts},
        "daily_roi": daily_rois,
        "weekly_roi": weekly_roi,
        "monthly_roi": monthly_roi,
        "insurance_hit_rate_mean": round(sum(hit_rates) / len(hit_rates), 8) if hit_rates else None,
        "coverage_gain_mean": round(sum(gains) / len(gains), 8) if gains else None,
        "days": [{"day_id": d[0], "prediction_date": d[1], "status": d[2]} for d in days],
        "forward_shadow_ready": True,
        "not_deployed": True,
    }


def write_forward_shadow_summary(summary: dict[str, Any], output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "forward_shadow_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return str(path)
