"""Research forward shadow for Betting Day Similarity — no real betting."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = {
    "research_only": True,
    "table": "betting_day_similarity_forward_shadow",
    "no_real_betting": True,
    "no_production_api": True,
    "no_ui_deployment": True,
}


def ensure_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS betting_day_similarity_forward_shadow (
                vienna_date TEXT PRIMARY KEY,
                feature_vector_json TEXT,
                similarity_score REAL,
                nearest_analogs_json TEXT,
                regime TEXT,
                ood_status TEXT,
                baseline_action TEXT,
                calibrated_action TEXT,
                overlay_action TEXT,
                capital_multiplier REAL,
                realized_roi REAL,
                coupon_survival REAL,
                insurance_rescue INTEGER,
                cumulative_drawdown REAL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def store_forward_day(path: Path, row: dict[str, Any]) -> None:
    ensure_db(path)
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            """
            INSERT OR REPLACE INTO betting_day_similarity_forward_shadow
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("vienna_date"),
                json.dumps(row.get("feature_vector") or {}),
                row.get("similarity_score"),
                json.dumps(row.get("nearest_analogs") or []),
                str(row.get("regime")),
                row.get("ood_status"),
                row.get("baseline_action"),
                row.get("calibrated_action"),
                row.get("overlay_action"),
                row.get("capital_multiplier"),
                row.get("realized_roi"),
                row.get("coupon_survival"),
                row.get("insurance_rescue"),
                row.get("cumulative_drawdown"),
            ),
        )
        con.commit()
    finally:
        con.close()


def summarize_forward(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"research_only": True, "n_days": 0, "days": []}
    con = sqlite3.connect(str(path))
    try:
        cur = con.execute("SELECT * FROM betting_day_similarity_forward_shadow ORDER BY vienna_date")
        cols = [d[0] for d in cur.description]
        days = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()
    return {"research_only": True, "n_days": len(days), "days": days, "schema": SCHEMA}
