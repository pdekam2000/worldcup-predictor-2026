"""PHASE ECSE-X3-B — Backfill owner shadow lab from M6 rows."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from worldcup_predictor.research.ecse_x2_m6.odds import build_probs_for_fixture
from worldcup_predictor.research.ecse_x2_m6.store import read_shadow_shortlists
from worldcup_predictor.research.ecse_x3_b.runtime import compute_x3_owner_shadow_row
from worldcup_predictor.research.ecse_x3_b.store import append_owner_shadow_row, read_owner_shadow_rows


def sync_from_m6_shadow(
    conn: sqlite3.Connection,
    *,
    limit: int = 50_000,
) -> dict[str, Any]:
    """Backfill X3-B artifact from existing M6 shadow-live rows."""
    m6_rows = read_shadow_shortlists(limit=limit)
    written = 0
    skipped = 0
    available = 0
    unavailable = 0
    rejected = 0

    for m6 in m6_rows:
        fid = int(m6.get("fixture_id") or 0)
        if not fid:
            continue
        baseline = m6.get("baseline_top10") or []
        if not baseline:
            skipped += 1
            continue

        prediction = {
            "top_10_scorelines": baseline,
            "kickoff_utc": m6.get("kickoff_time"),
            "competition_key": m6.get("league") or m6.get("tournament"),
        }
        probs, _, snap_id = build_probs_for_fixture(conn, fid, prediction)
        snap_id = m6.get("odds_snapshot_id") or snap_id

        row = compute_x3_owner_shadow_row(
            fixture_id=fid,
            baseline_top10=baseline,
            probs=probs,
            odds_snapshot_id=snap_id,
            m5_shadow=m6 if m6.get("applied") else {"applied": m6.get("applied"), "enhanced_top10": m6.get("enhanced_top10")},
            fixture_metadata={
                "kickoff_utc": m6.get("kickoff_time"),
                "league": m6.get("league"),
            },
        )
        ok, reason = append_owner_shadow_row(row)
        if ok:
            written += 1
        else:
            skipped += 1
        st = row.get("x3_status")
        if st == "available":
            available += 1
        elif st == "rejected":
            rejected += 1
        else:
            unavailable += 1

    return {
        "m6_rows_processed": len(m6_rows),
        "rows_written": written,
        "rows_skipped": skipped,
        "x3_available": available,
        "x3_unavailable": unavailable,
        "x3_rejected": rejected,
    }
