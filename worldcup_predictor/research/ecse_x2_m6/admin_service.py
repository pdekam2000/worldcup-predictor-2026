"""PHASE ECSE-X2-M6 — Admin read service for shadow-live shortlists."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m6.store import (
    _artifact_path,
    get_shadow_shortlist_for_fixture,
    read_shadow_shortlists,
)


class EcseX2ShadowLiveService:
    def list_shortlists(
        self,
        *,
        status: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = read_shadow_shortlists(limit=10_000)
        if status == "pending":
            rows = [r for r in rows if r.get("evaluation_status") == "pending"]
        elif status == "evaluated":
            rows = [r for r in rows if r.get("evaluation_status") == "evaluated"]
        elif status == "applied":
            rows = [r for r in rows if r.get("applied")]
        total = len(rows)
        page = rows[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_public_item(r) for r in page],
        }

    def get_fixture(self, fixture_id: int) -> dict[str, Any] | None:
        row = get_shadow_shortlist_for_fixture(fixture_id)
        if not row:
            return None
        eval_row = _load_eval_for_fixture(fixture_id)
        return {
            **_public_item(row),
            "evaluation": eval_row,
        }

    def summary(self) -> dict[str, Any]:
        rows = read_shadow_shortlists(limit=50_000)
        applied = sum(1 for r in rows if r.get("applied"))
        strong = sum(1 for r in rows if r.get("strong_segment"))
        pending = sum(1 for r in rows if r.get("evaluation_status") == "pending")
        exclusions: dict[str, int] = {}
        for r in rows:
            if not r.get("applied"):
                reason = str(r.get("exclusion_reason") or "unknown")
                exclusions[reason] = exclusions.get(reason, 0) + 1
        return {
            "total_rows": len(rows),
            "applied_count": applied,
            "strong_segment_count": strong,
            "pending_evaluation": pending,
            "exclusion_reasons": exclusions,
            "artifact": SHADOW_ARTIFACT,
        }


def _public_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": row.get("fixture_id"),
        "kickoff_time": row.get("kickoff_time"),
        "league": row.get("league"),
        "tournament": row.get("tournament"),
        "generated_at": row.get("generated_at"),
        "odds_snapshot_id": row.get("odds_snapshot_id"),
        "home_prob": row.get("home_prob"),
        "segment_labels": row.get("segment_labels"),
        "strong_segment": row.get("strong_segment"),
        "applied": row.get("applied"),
        "exclusion_reason": row.get("exclusion_reason"),
        "baseline_top10": row.get("baseline_top10"),
        "enhanced_top10": row.get("enhanced_top10"),
        "rank_movements": row.get("rank_movements"),
        "evaluation_status": row.get("evaluation_status"),
        "public_output_changed": row.get("public_output_changed", False),
        "audit_trace": row.get("audit_trace"),
    }


def _load_eval_for_fixture(fixture_id: int) -> dict[str, Any] | None:
    path = _artifact_path(EVAL_ARTIFACT)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if int(row.get("fixture_id") or 0) == int(fixture_id):
                return row
        except json.JSONDecodeError:
            continue
    return None
