"""Prematch feature coverage measurement."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.provider_features.mapping import OWNER_SCOPE_MATRIX_KEYS, competition_meta
from worldcup_predictor.provider_features.repository import count_snapshots, ensure_tables


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def measure_coverage(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_tables(conn)
    completed = int(
        conn.execute(
            "SELECT COUNT(*) FROM fixtures f JOIN fixture_results r ON r.fixture_id=f.fixture_id"
        ).fetchone()[0]
    )
    upcoming = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM fixtures
            WHERE status IN ('NS','TBD','SCHEDULED','TIMED','Not Started')
            AND datetime(kickoff_utc) > datetime('now')
            """
        ).fetchone()[0]
    )

    families = ("lineup", "injury", "xg_prematch", "form")
    before_after: dict[str, Any] = {}
    for fam in families:
        total = count_snapshots(conn, feature_family=fam)
        safe = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM prematch_feature_snapshots
                WHERE feature_family = ? AND leakage_status IN ('SAFE_PREMATCH', 'FUTURE_SNAPSHOT_ONLY')
                """,
                (fam,),
            ).fetchone()[0]
        )
        rejected = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM prematch_feature_snapshots
                WHERE feature_family = ? AND leakage_status IN ('REJECTED', 'POST_MATCH_ONLY', 'TIMESTAMP_PROVENANCE_INSUFFICIENT')
                """,
                (fam,),
            ).fetchone()[0]
        )
        before_after[fam] = {
            "snapshots_stored": total,
            "timestamp_valid": safe,
            "leakage_rejected": rejected,
            "coverage_pct_completed": round(100.0 * safe / completed, 2) if completed else 0.0,
        }

    by_competition: list[dict[str, Any]] = []
    for key in OWNER_SCOPE_MATRIX_KEYS:
        meta = competition_meta(key)
        elig = conn.execute(
            "SELECT COUNT(*) FROM fixtures WHERE competition_key = ?",
            (key,),
        ).fetchone()[0]
        with_snap = conn.execute(
            """
            SELECT COUNT(DISTINCT fixture_id) FROM prematch_feature_snapshots
            WHERE competition_key = ?
            """,
            (key,),
        ).fetchone()[0]
        by_competition.append(
            {
                "competition_key": key,
                "tier": meta.get("tier"),
                "eligible_fixtures": int(elig),
                "fixtures_with_any_snapshot": int(with_snap),
            }
        )

    return {
        "measured_at_utc": _utc_now(),
        "completed_fixtures": completed,
        "upcoming_fixtures": upcoming,
        "feature_families": before_after,
        "by_competition": by_competition,
        "thresholds": {
            "xg_research_min_pct": 5,
            "xg_league_min_pct": 20,
            "lineup_shadow_min_pct": 10,
        },
    }
