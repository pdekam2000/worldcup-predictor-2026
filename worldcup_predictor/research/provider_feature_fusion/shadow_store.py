"""Isolated shadow output storage — never touches production predictions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.provider_feature_fusion.constants import (
    FEATURE_VERSION,
    MODEL_VERSION,
    SHADOW_OUTPUT_DIR,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DDL = """
CREATE TABLE IF NOT EXISTS provider_feature_fusion_shadow (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id TEXT NOT NULL,
    baseline_prediction TEXT,
    fusion_prediction TEXT,
    baseline_probabilities_json TEXT,
    fusion_probabilities_json TEXT,
    feature_families_used TEXT,
    missing_features TEXT,
    shadow_confidence REAL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    evaluation_status TEXT NOT NULL DEFAULT 'pending',
    production_visible INTEGER NOT NULL DEFAULT 0,
    variant TEXT NOT NULL,
    UNIQUE(fixture_id, variant, model_version)
);
"""


def ensure_shadow_table(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    conn.commit()


def write_shadow_batch(
    rows: list[dict[str, Any]],
    *,
    db_path: str | Path,
    variant: str,
) -> int:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        ensure_shadow_table(conn)
        written = 0
        for row in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO provider_feature_fusion_shadow (
                    fixture_id, baseline_prediction, fusion_prediction,
                    baseline_probabilities_json, fusion_probabilities_json,
                    feature_families_used, missing_features, shadow_confidence,
                    model_version, feature_version, generated_at, evaluation_status,
                    production_visible, variant
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    str(row.get("fixture_id")),
                    row.get("baseline_prediction"),
                    row.get("fusion_prediction"),
                    json.dumps(row.get("baseline_probabilities") or {}),
                    json.dumps(row.get("fusion_probabilities") or {}),
                    json.dumps(row.get("feature_families_used") or []),
                    json.dumps(row.get("missing_features") or []),
                    row.get("shadow_confidence"),
                    MODEL_VERSION,
                    FEATURE_VERSION,
                    _utc_now(),
                    row.get("evaluation_status", "holdout_evaluated"),
                    variant,
                ),
            )
            written += 1
        conn.commit()
        return written
    finally:
        conn.close()


def export_shadow_jsonl(rows: list[dict[str, Any]], *, variant: str) -> Path:
    SHADOW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = SHADOW_OUTPUT_DIR / f"fusion_shadow_{variant}_{stamp}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            rec = {**row, "production_visible": False, "model_version": MODEL_VERSION, "feature_version": FEATURE_VERSION}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out
