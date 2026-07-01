"""PHASE ECSE-X3-B — j2_g_slope shadow runtime for owner lab."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.research.ecse_x3.mapping import apply_j2_g_slope_shadow
from worldcup_predictor.research.ecse_x3_b.constants import CANDIDATE_ID, REQUIRED_PROB_KEYS


def _top_n_slice(rows: list[dict[str, Any]] | None, n: int) -> list[str]:
    if not rows:
        return []
    return [str(r["scoreline"]) for r in sorted(rows, key=lambda x: int(x["rank"]))[:n]]


def _odds_coverage_fields(probs: dict[str, float | None]) -> dict[str, bool]:
    return {k: probs.get(k) is not None for k in REQUIRED_PROB_KEYS}


def compute_x3_owner_shadow_row(
    *,
    fixture_id: int,
    baseline_top10: list[dict[str, Any]],
    probs: dict[str, float | None],
    odds_snapshot_id: int | None = None,
    m5_shadow: dict[str, Any] | None = None,
    fixture_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build owner shadow lab artifact row; never mutates baseline."""
    meta = fixture_metadata or {}
    shadow = apply_j2_g_slope_shadow(baseline_top10, probs)
    baseline_top = shadow.get("baseline_top10") or []
    x3_top = shadow.get("x3_top10") or baseline_top
    status = shadow.get("x3_status") or "unavailable"

    m5_top = None
    m5_applied = False
    if m5_shadow:
        m5_applied = bool(m5_shadow.get("applied"))
        m5_top = m5_shadow.get("enhanced_top10")

    return {
        "fixture_id": fixture_id,
        "kickoff_time": meta.get("kickoff_utc") or meta.get("kickoff_time"),
        "league": meta.get("league") or meta.get("competition_key"),
        "baseline_method": "ecse_baseline",
        "baseline_top1": _top_n_slice(baseline_top, 1)[0] if baseline_top else None,
        "baseline_top3": _top_n_slice(baseline_top, 3),
        "baseline_top10": baseline_top,
        "m5_shadow_applied": m5_applied,
        "m5_shadow_result": m5_top,
        "m5_shadow_top1": _top_n_slice(m5_top, 1)[0] if m5_top else None,
        "x3_candidate": CANDIDATE_ID,
        "x3_status": status,
        "x3_top1": _top_n_slice(x3_top, 1)[0] if x3_top and status == "available" else None,
        "x3_top3": _top_n_slice(x3_top, 3) if status == "available" else [],
        "x3_top5": _top_n_slice(x3_top, 5) if status == "available" else [],
        "x3_top10": x3_top if status == "available" else None,
        "j2": shadow.get("j2"),
        "g": shadow.get("g"),
        "ou_slope": shadow.get("ou_slope"),
        "odds_coverage_fields": _odds_coverage_fields(probs),
        "missing_fields": shadow.get("missing_fields") or [],
        "rejection_reason": shadow.get("rejection_reason"),
        "rank_movements": shadow.get("rank_movements") or {},
        "odds_snapshot_id": odds_snapshot_id,
        "public_prediction_changed": False,
    }


def assert_no_nan_inf(row: dict[str, Any]) -> bool:
    for key in ("j2", "g", "ou_slope"):
        val = row.get(key)
        if val is not None and (not math.isfinite(float(val))):
            return False
    return True
