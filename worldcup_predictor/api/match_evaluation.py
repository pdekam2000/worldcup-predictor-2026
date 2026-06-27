"""Production match evaluation summary for API display (read-only)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.api.archive_evaluation_join import (
    compute_row_status_from_evaluation,
    count_market_statuses,
    is_quarantined_evaluation,
    market_statuses_from_evaluation_row,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

RESULT_COLORS: dict[str, str] = {
    "correct": "green",
    "wrong": "red",
    "partial": "purple",
    "pending": "yellow",
    "unknown": "gray",
    "void": "gray",
}


def evaluation_summary_from_row(
    row: dict[str, Any] | None,
    *,
    include_quarantined: bool = False,
) -> dict[str, Any] | None:
    if not row:
        return None
    if is_quarantined_evaluation(row) and not include_quarantined:
        return None
    market_statuses = market_statuses_from_evaluation_row(
        row,
        include_quarantined=include_quarantined,
    )
    row_status, row_reason = compute_row_status_from_evaluation(
        row,
        include_quarantined=include_quarantined,
    )
    counts = count_market_statuses(market_statuses)
    market_colors = {k: RESULT_COLORS.get(v, "gray") for k, v in market_statuses.items()}
    return {
        "fixture_id": int(row.get("fixture_id") or 0),
        "result_status": row_status,
        "evaluation_status": row_status,
        "row_status_reason": row_reason,
        "actual_result": row.get("actual_result"),
        "final_score": row.get("final_score"),
        "evaluated_at": row.get("evaluated_at"),
        "is_finished": row_status in {"correct", "wrong", "partial"},
        "market_statuses": market_statuses,
        "market_colors": market_colors,
        "overall_status": row.get("overall_status"),
        "is_quarantined": is_quarantined_evaluation(row),
        "source": "worldcup_prediction_evaluations",
        **counts,
    }


def get_production_evaluation_summary(
    fixture_id: int,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Load evaluation row and map to UI-friendly summary (no engine changes)."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    try:
        row = repo.get_worldcup_prediction_evaluation(int(fixture_id))
        if not row or is_quarantined_evaluation(row):
            return None

        return evaluation_summary_from_row(row)
    finally:
        repo.close()


def attach_match_evaluation(payload: dict[str, Any], *, settings: Settings | None = None) -> dict[str, Any]:
    """Attach production evaluation block to a prediction payload when available."""
    out = dict(payload)
    fixture_id = int(out.get("fixture_id") or 0)
    if fixture_id <= 0:
        return out
    summary = get_production_evaluation_summary(fixture_id, settings=settings)
    if summary:
        out["match_evaluation"] = summary
        out["result_status"] = summary.get("result_status")
        out["evaluation_status"] = summary.get("evaluation_status")
        out["final_score"] = summary.get("final_score") or out.get("final_score")
        out["actual_result"] = summary.get("actual_result") or out.get("actual_result")
    return out
