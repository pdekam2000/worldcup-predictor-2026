"""Isolated Lambda V2 / Exact V2 shadow persistence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE

SHADOW_DDL = f"""
CREATE TABLE IF NOT EXISTS {SHADOW_TABLE} (
    shadow_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    canonical_prediction_id TEXT,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_schema_version TEXT,
    feature_cutoff TEXT,
    history_count_home INTEGER,
    history_count_away INTEGER,
    missing_count INTEGER,
    fallback_count INTEGER,
    odds_freshness TEXT,
    totals_lines_json TEXT,
    lambda_home REAL,
    lambda_away REAL,
    lambda_uncertainty REAL,
    score_distribution_type TEXT,
    top1 TEXT,
    top5_json TEXT,
    top10_json TEXT,
    top5_mass REAL,
    entropy REAL,
    wde_direction_mass REAL,
    btts_mass REAL,
    ou_mass REAL,
    payload_json TEXT,
    shadow_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(fixture_id, model_id, shadow_hash)
)
"""


def ensure_shadow_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SHADOW_DDL)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2_shadow_fx ON {SHADOW_TABLE}(fixture_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2_shadow_model ON {SHADOW_TABLE}(model_id)")
    conn.commit()


def persist_shadow(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    model_id: str,
    model_version: str,
    lambda_home: float,
    lambda_away: float,
    tops: list[str],
    dist_type: str,
    meta: dict[str, Any],
    canonical_prediction_id: str | None = None,
) -> str:
    ensure_shadow_schema(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    payload = {
        "fixture_id": fixture_id,
        "model_id": model_id,
        "model_version": model_version,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "tops": tops,
        "dist_type": dist_type,
        "meta": meta,
        "canonical": False,
        "shadow_only": True,
    }
    h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    sid = f"l2-{fixture_id}-{model_id}-{h[:12]}"
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {SHADOW_TABLE} (
            shadow_id, fixture_id, canonical_prediction_id, model_id, model_version,
            feature_schema_version, feature_cutoff, history_count_home, history_count_away,
            missing_count, fallback_count, odds_freshness, totals_lines_json,
            lambda_home, lambda_away, lambda_uncertainty, score_distribution_type,
            top1, top5_json, top10_json, top5_mass, entropy, wde_direction_mass,
            btts_mass, ou_mass, payload_json, shadow_hash, created_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            sid,
            int(fixture_id),
            canonical_prediction_id,
            model_id,
            model_version,
            meta.get("feature_schema_version"),
            meta.get("feature_cutoff"),
            meta.get("history_count_home"),
            meta.get("history_count_away"),
            meta.get("missing_count"),
            meta.get("fallback_count"),
            meta.get("odds_freshness"),
            json.dumps(meta.get("totals_lines") or []),
            float(lambda_home),
            float(lambda_away),
            meta.get("lambda_uncertainty"),
            dist_type,
            tops[0] if tops else None,
            json.dumps(tops[:5]),
            json.dumps(tops[:10]),
            meta.get("top5_mass"),
            meta.get("entropy"),
            meta.get("wde_direction_mass"),
            meta.get("btts_mass"),
            meta.get("ou_mass"),
            json.dumps(payload, default=str),
            h,
            now,
        ),
    )
    conn.commit()
    return sid
