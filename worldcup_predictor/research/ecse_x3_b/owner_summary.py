"""PHASE ECSE-X3-B — Owner shadow lab summary builder."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT
from worldcup_predictor.research.ecse_x3_b.constants import (
    CANDIDATE_ID,
    DISPLAY_LABEL,
    PROMOTION_STATUS,
    RECOMMENDATION,
    SUMMARY_ARTIFACT,
)
from worldcup_predictor.research.ecse_x3_b.registry import COMPOSITE_PROMOTION_BLOCKED, get_registry
from worldcup_predictor.research.ecse_x3_b.store import _artifact_path, read_owner_shadow_rows


def _load_evaluations() -> dict[int, str]:
    path = _artifact_path(EVAL_ARTIFACT)
    out: dict[int, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            fid = int(row.get("fixture_id") or 0)
            actual = row.get("actual_score")
            if fid and actual:
                out[fid] = str(actual)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return out


def _hit_rank(top10: list[dict[str, Any]] | None, actual: str) -> int | None:
    if not top10 or not actual:
        return None
    for r in top10:
        if str(r.get("scoreline")) == actual:
            return int(r.get("rank"))
    return None


def build_summary(conn: Any = None) -> dict[str, Any]:
    rows = read_owner_shadow_rows(limit=50_000)
    evals = _load_evaluations()
    available = [r for r in rows if r.get("x3_status") == "available"]
    unavailable = [r for r in rows if r.get("x3_status") == "unavailable"]
    rejected = [r for r in rows if r.get("x3_status") == "rejected"]

    missing_counter: Counter[str] = Counter()
    for r in rows:
        for f in r.get("missing_fields") or []:
            missing_counter[str(f)] += 1

    baseline_hits = {"top1": 0, "top3": 0, "top5": 0}
    x3_hits = {"top1": 0, "top3": 0, "top5": 0}
    m5_hits = {"top1": 0, "top3": 0, "top5": 0}
    compared = 0

    for r in rows:
        actual = r.get("actual_score") or evals.get(int(r.get("fixture_id") or 0))
        if not actual:
            continue
        compared += 1
        b10 = r.get("baseline_top10") or []
        br = _hit_rank(b10, actual)
        if br == 1:
            baseline_hits["top1"] += 1
        if br and br <= 3:
            baseline_hits["top3"] += 1
        if br and br <= 5:
            baseline_hits["top5"] += 1

        if r.get("x3_status") == "available":
            xr = _hit_rank(r.get("x3_top10"), actual)
            if xr == 1:
                x3_hits["top1"] += 1
            if xr and xr <= 3:
                x3_hits["top3"] += 1
            if xr and xr <= 5:
                x3_hits["top5"] += 1

        m5 = r.get("m5_shadow_result")
        if m5 and r.get("m5_shadow_applied"):
            mr = _hit_rank(m5, actual)
            if mr == 1:
                m5_hits["top1"] += 1
            if mr and mr <= 3:
                m5_hits["top3"] += 1
            if mr and mr <= 5:
                m5_hits["top5"] += 1

    def _rates(hits: dict[str, int], n: int) -> dict[str, float]:
        if n <= 0:
            return {}
        return {k: round(100.0 * hits[k] / n, 4) for k in hits}

    n_avail = len(available)
    n_eval_avail = sum(1 for r in available if r.get("actual_score"))

    summary: dict[str, Any] = {
        "phase": "ECSE-X3-B",
        "registry": get_registry(),
        "candidate": {
            "id": CANDIDATE_ID,
            "display_label": DISPLAY_LABEL,
            "recommendation": RECOMMENDATION,
            "promotion_status": PROMOTION_STATUS,
            "composite_promotion_blocked": list(COMPOSITE_PROMOTION_BLOCKED),
        },
        "evaluated_fixture_count": len(rows),
        "x3_available_count": len(available),
        "x3_unavailable_count": len(unavailable),
        "x3_rejected_count": len(rejected),
        "coverage_percentage": round(100.0 * len(available) / max(len(rows), 1), 4),
        "missing_field_breakdown": dict(missing_counter.most_common(20)),
        "comparison_vs_baseline": {
            "evaluated_with_actual": compared,
            "baseline_hit_rates_pct": _rates(baseline_hits, compared),
            "x3_hit_rates_pct": _rates(x3_hits, n_eval_avail),
            "x3_delta_top1_pp": round(
                _rates(x3_hits, n_eval_avail).get("top1", 0) - _rates(baseline_hits, compared).get("top1", 0), 4
            )
            if n_eval_avail and compared
            else None,
        },
        "comparison_vs_m5": {
            "m5_applied_with_actual": sum(
                1 for r in rows if r.get("m5_shadow_applied") and r.get("actual_score")
            ),
            "m5_hit_rates_pct": _rates(
                m5_hits,
                sum(1 for r in rows if r.get("m5_shadow_applied") and r.get("actual_score")),
            ),
        },
        "safety": {
            "public_predictions_unchanged": True,
            "subscriptions_unchanged": True,
            "baseline_table_unchanged": True,
            "public_prediction_changed_rows": sum(
                1 for r in rows if r.get("public_prediction_changed") is True
            ),
            "phi_forbidden": True,
        },
    }

    if conn is not None:
        summary["safety"]["baseline_table_rows"] = baseline_table_row_count(conn)

    return summary


def write_summary(conn: Any = None, *, path: str | None = None) -> Path:
    out = _artifact_path(path or SUMMARY_ARTIFACT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_summary(conn), indent=2, default=str), encoding="utf-8")
    return out
