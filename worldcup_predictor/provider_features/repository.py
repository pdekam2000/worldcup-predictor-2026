"""Immutable idempotent prematch feature snapshot repository."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.provider_features.ddl import PREMATCH_FEATURE_DDL
from worldcup_predictor.provider_features.models import PrematchFeatureSnapshot
from worldcup_predictor.provider_features.timestamp_policy import LeakageStatus, admissible_for_store


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_tables(conn: sqlite3.Connection) -> None:
    for ddl in PREMATCH_FEATURE_DDL:
        conn.execute(ddl)
    conn.commit()


def _snapshot_key(snap: PrematchFeatureSnapshot) -> str:
    raw = "|".join(
        [
            str(snap.fixture_id),
            snap.provider,
            snap.feature_family,
            snap.feature_name,
            snap.feature_version,
            snap.feature_available_at_utc,
            snap.source_endpoint or "",
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def insert_snapshot(conn: sqlite3.Connection, snap: PrematchFeatureSnapshot, *, allow_future: bool = True) -> str:
    status = LeakageStatus(snap.leakage_status) if snap.leakage_status in LeakageStatus._value2member_map_ else LeakageStatus.REJECTED
    if not admissible_for_store(status, allow_future_snapshot=allow_future):
        return "rejected_leakage"

    key = _snapshot_key(snap)
    payload = {
        "feature_value": snap.feature_value,
        "extra_values": snap.extra_values,
    }
    phash = _payload_hash(payload)
    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO prematch_feature_snapshots (
                snapshot_key, fixture_id, competition_key, tier, provider, provider_fixture_id,
                feature_family, feature_name, feature_version, feature_available_at_utc,
                fetched_at_utc, prediction_cutoff_utc, kickoff_utc, source_endpoint,
                source_version, leakage_status, mapping_confidence, data_quality,
                completeness_mask, payload_hash, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                snap.fixture_id,
                snap.competition_key,
                snap.tier,
                snap.provider,
                snap.provider_fixture_id,
                snap.feature_family,
                snap.feature_name,
                snap.feature_version,
                snap.feature_available_at_utc,
                snap.fetched_at_utc,
                snap.prediction_cutoff_utc,
                snap.kickoff_utc,
                snap.source_endpoint,
                snap.source_version,
                snap.leakage_status,
                snap.mapping_confidence,
                snap.data_quality,
                json.dumps(snap.completeness_mask),
                phash,
                json.dumps(payload, ensure_ascii=False, default=str),
                _utc_now(),
            ),
        )
        conn.commit()
        return "inserted" if cur.rowcount else "duplicate"
    except sqlite3.IntegrityError:
        return "duplicate"


def count_snapshots(conn: sqlite3.Connection, *, feature_family: str | None = None) -> int:
    if feature_family:
        row = conn.execute(
            "SELECT COUNT(*) FROM prematch_feature_snapshots WHERE feature_family = ?",
            (feature_family,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM prematch_feature_snapshots").fetchone()
    return int(row[0]) if row else 0


def update_checkpoint(
    conn: sqlite3.Connection,
    *,
    phase: str,
    last_fixture_id: int | None,
    api_calls: int,
    sportmonks_calls: int,
) -> None:
    conn.execute(
        """
        INSERT INTO prematch_feature_backfill_checkpoint (id, phase, last_fixture_id, api_calls_used, sportmonks_calls_used, updated_at_utc)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            phase=excluded.phase,
            last_fixture_id=excluded.last_fixture_id,
            api_calls_used=excluded.api_calls_used,
            sportmonks_calls_used=excluded.sportmonks_calls_used,
            updated_at_utc=excluded.updated_at_utc
        """,
        (phase, last_fixture_id, api_calls, sportmonks_calls, _utc_now()),
    )
    conn.commit()
