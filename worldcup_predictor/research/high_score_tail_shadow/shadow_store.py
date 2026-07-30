"""Shadow persistence for high-score tail research — never mutates canonical freezes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SHADOW_DDL = """
CREATE TABLE IF NOT EXISTS high_score_tail_shadow_outputs (
    shadow_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    canonical_prediction_id TEXT,
    kickoff TEXT,
    frozen_at_utc TEXT NOT NULL,
    model_family TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_schema_version TEXT,
    regime TEXT,
    selector_confidence REAL,
    selector_reasons_json TEXT,
    top1 TEXT,
    top5_json TEXT,
    top10_json TEXT,
    top5_mass REAL,
    tail_mass_4plus REAL,
    other_mass REAL,
    lambda_home REAL,
    lambda_away REAL,
    odds_freshness TEXT,
    payload_json TEXT,
    shadow_hash TEXT NOT NULL,
    UNIQUE(fixture_id, model_family, shadow_hash)
)
"""

SHADOW_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_hst_shadow_fixture ON high_score_tail_shadow_outputs(fixture_id)",
    "CREATE INDEX IF NOT EXISTS idx_hst_shadow_family ON high_score_tail_shadow_outputs(model_family)",
)


def ensure_shadow_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SHADOW_DDL)
    for idx in SHADOW_INDEXES:
        try:
            conn.execute(idx)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def shadow_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persist_shadow_output(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    canonical_prediction_id: str | None,
    kickoff: str | None,
    model_family: str,
    model_version: str,
    tops: list[str],
    dist_summary: dict[str, Any],
    regime: str | None = None,
    selector: dict[str, Any] | None = None,
    lambda_home: float | None = None,
    lambda_away: float | None = None,
    odds_freshness: str | None = None,
    feature_schema_version: str = "hst-shadow-v1",
) -> str:
    """Insert shadow row. Never touches frozen_predictions."""
    ensure_shadow_schema(conn)
    payload = {
        "fixture_id": int(fixture_id),
        "model_family": model_family,
        "model_version": model_version,
        "tops": tops,
        "dist_summary": dist_summary,
        "regime": regime,
        "selector": selector,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
    }
    h = shadow_hash(payload)
    shadow_id = f"hst-{fixture_id}-{model_family}-{h[:12]}"
    conn.execute(
        """
        INSERT OR IGNORE INTO high_score_tail_shadow_outputs (
            shadow_id, fixture_id, canonical_prediction_id, kickoff, frozen_at_utc,
            model_family, model_version, feature_schema_version, regime,
            selector_confidence, selector_reasons_json,
            top1, top5_json, top10_json, top5_mass, tail_mass_4plus, other_mass,
            lambda_home, lambda_away, odds_freshness, payload_json, shadow_hash
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            shadow_id,
            int(fixture_id),
            canonical_prediction_id,
            kickoff,
            _utc_now(),
            model_family,
            model_version,
            feature_schema_version,
            regime,
            (selector or {}).get("selector_confidence"),
            json.dumps((selector or {}).get("reasons") or [], default=str),
            tops[0] if tops else None,
            json.dumps(tops[:5], default=str),
            json.dumps(tops[:10], default=str),
            dist_summary.get("top5_mass"),
            dist_summary.get("tail_mass_4plus"),
            dist_summary.get("other_mass"),
            lambda_home,
            lambda_away,
            odds_freshness,
            json.dumps(payload, default=str),
            h,
        ),
    )
    conn.commit()
    return shadow_id
