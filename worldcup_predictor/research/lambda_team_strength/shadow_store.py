"""Isolated shadow persistence for lambda team-strength challengers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SHADOW_DDL = """
CREATE TABLE IF NOT EXISTS lambda_team_strength_shadow_outputs (
    shadow_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    canonical_prediction_id TEXT,
    kickoff TEXT,
    frozen_at_utc TEXT NOT NULL,
    challenger_model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT,
    feature_freshness TEXT,
    missingness_count INTEGER,
    fallback_count INTEGER,
    lambda_home REAL,
    lambda_away REAL,
    lambda_uncertainty REAL,
    regime TEXT,
    reasons_json TEXT,
    top1 TEXT,
    top5_json TEXT,
    top10_json TEXT,
    top5_mass REAL,
    probability_mass REAL,
    odds_freshness TEXT,
    prediction_timestamp TEXT,
    payload_json TEXT,
    shadow_hash TEXT NOT NULL,
    UNIQUE(fixture_id, challenger_model_id, shadow_hash)
)
"""


def ensure_shadow_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SHADOW_DDL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lts_shadow_fixture "
        "ON lambda_team_strength_shadow_outputs(fixture_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lts_shadow_model "
        "ON lambda_team_strength_shadow_outputs(challenger_model_id)"
    )
    conn.commit()


def shadow_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persist_shadow_output(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    canonical_prediction_id: str | None,
    kickoff: str | None,
    challenger_model_id: str,
    model_version: str,
    lambda_home: float,
    lambda_away: float,
    tops: list[str],
    dist_summary: dict[str, Any],
    feature_version: str = "lts-features-v1",
    feature_freshness: str | None = None,
    missingness_count: int = 0,
    fallback_count: int = 0,
    lambda_uncertainty: float | None = None,
    regime: str | None = None,
    reasons: list[str] | None = None,
    odds_freshness: str | None = None,
) -> str:
    ensure_shadow_schema(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    payload = {
        "fixture_id": int(fixture_id),
        "challenger_model_id": challenger_model_id,
        "model_version": model_version,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "lambda_uncertainty": lambda_uncertainty,
        "tops": tops,
        "dist_summary": dist_summary,
        "regime": regime,
        "reasons": reasons or [],
        "canonical": False,
        "shadow_only": True,
    }
    h = shadow_hash(payload)
    shadow_id = f"lts-{fixture_id}-{challenger_model_id}-{h[:12]}"
    conn.execute(
        """
        INSERT OR IGNORE INTO lambda_team_strength_shadow_outputs (
            shadow_id, fixture_id, canonical_prediction_id, kickoff, frozen_at_utc,
            challenger_model_id, model_version, feature_version, feature_freshness,
            missingness_count, fallback_count, lambda_home, lambda_away, lambda_uncertainty,
            regime, reasons_json, top1, top5_json, top10_json, top5_mass, probability_mass,
            odds_freshness, prediction_timestamp, payload_json, shadow_hash
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            shadow_id,
            int(fixture_id),
            canonical_prediction_id,
            kickoff,
            now,
            challenger_model_id,
            model_version,
            feature_version,
            feature_freshness,
            int(missingness_count),
            int(fallback_count),
            float(lambda_home),
            float(lambda_away),
            lambda_uncertainty,
            regime,
            json.dumps(reasons or []),
            tops[0] if tops else None,
            json.dumps(tops[:5]),
            json.dumps(tops[:10]),
            dist_summary.get("top5_mass"),
            dist_summary.get("probability_mass", 1.0),
            odds_freshness,
            now,
            json.dumps(payload, default=str),
            h,
        ),
    )
    conn.commit()
    return shadow_id
