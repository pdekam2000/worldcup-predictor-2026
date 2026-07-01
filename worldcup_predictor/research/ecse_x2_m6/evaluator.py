"""PHASE ECSE-X2-M6 — Shadow shortlist evaluation when results available."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_x2_m5.metrics import hit_positions
from worldcup_predictor.research.ecse_x2_m6.constants import METHOD_VERSION
from worldcup_predictor.research.ecse_x2_m6.store import (
    append_shadow_evaluation,
    get_shadow_shortlist_for_fixture,
    read_shadow_shortlists,
)


def evaluate_shadow_shortlist_row(
    shadow_row: dict[str, Any],
    *,
    actual_score: str,
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    baseline = shadow_row.get("baseline_top10") or shadow_row.get("baseline_top_10") or []
    enhanced = shadow_row.get("enhanced_top10") or shadow_row.get("enhanced_top_10") or []
    base_hits = hit_positions(baseline, actual_score)
    enh_hits = hit_positions(enhanced, actual_score)

    return {
        "fixture_id": int(shadow_row["fixture_id"]),
        "snapshot_id": snapshot_id or shadow_row.get("snapshot_id"),
        "actual_score": actual_score,
        "applied": bool(shadow_row.get("applied")),
        "baseline_hits": base_hits,
        "enhanced_hits": enh_hits,
        "delta": {
            "top1": int(enh_hits["hit_top1"]) - int(base_hits["hit_top1"]),
            "top3": int(enh_hits["hit_top3"]) - int(base_hits["hit_top3"]),
            "top5": int(enh_hits["hit_top5"]) - int(base_hits["hit_top5"]),
            "top10": int(enh_hits["hit_top10"]) - int(base_hits["hit_top10"]),
            "reciprocal_rank": round(
                enh_hits["reciprocal_rank"] - base_hits["reciprocal_rank"], 6
            ),
            "actual_rank_delta": (
                (base_hits["actual_rank"] or 0) - (enh_hits["actual_rank"] or 0)
                if base_hits["actual_rank"] and enh_hits["actual_rank"]
                else None
            ),
        },
        "segment_labels": shadow_row.get("segment_labels") or [],
        "method_version": METHOD_VERSION,
        "evaluation_status": "evaluated",
    }


def evaluate_fixture_shadow(
    fixture_id: int,
    *,
    actual_score: str,
    snapshot_id: int | None = None,
) -> dict[str, Any] | None:
    shadow = get_shadow_shortlist_for_fixture(fixture_id)
    if not shadow:
        return None
    payload = evaluate_shadow_shortlist_row(
        shadow, actual_score=actual_score, snapshot_id=snapshot_id
    )
    append_shadow_evaluation(payload)
    return payload


def backfill_evaluations_from_snapshots(
    conn,
    *,
    limit: int = 500,
) -> dict[str, Any]:
    """Evaluate shadow rows for finished fixtures with ECSE live evaluations."""
    from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables

    ensure_ecse_live_tables(conn)
    rows = conn.execute(
        """
        SELECT e.fixture_id, e.final_score, e.snapshot_id
        FROM ecse_prediction_evaluations e
        ORDER BY e.evaluated_at DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    evaluated = 0
    skipped = 0
    for row in rows:
        fid = int(row["fixture_id"])
        score = str(row["final_score"])
        sid = int(row["snapshot_id"])
        if evaluate_fixture_shadow(fid, actual_score=score, snapshot_id=sid):
            evaluated += 1
        else:
            skipped += 1

    return {"evaluated": evaluated, "skipped": skipped, "scanned": len(rows)}
