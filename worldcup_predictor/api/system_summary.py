"""Phase 49A — honest system-wide counts for dashboard and landing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.performance_center import build_performance_summary
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def build_system_summary(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    archived_total = repo.count_worldcup_stored_predictions(
        competition_key=competition_key,
        include_quarantined=False,
    )
    legacy_rows = repo.list_worldcup_stored_prediction_rows(competition_key=competition_key)
    legacy_import_count = sum(
        1 for row in legacy_rows if str(row.get("source") or "").lower() == "legacy_import"
    )

    perf = build_performance_summary(competition_key=competition_key)
    evaluated = int(perf.get("correct_count") or 0) + int(perf.get("wrong_count") or 0)
    pending = int(perf.get("pending_count") or 0)

    best_tips_available = bool((perf.get("best_tips_preview") or perf.get("markets")))

    return {
        "status": "ok",
        "competition": competition_key,
        "archive": {
            "total_predictions": archived_total,
            "legacy_import_count": legacy_import_count,
            "includes_global_system_predictions": True,
        },
        "evaluation": {
            "finished_evaluated": evaluated,
            "pending": pending,
            "overall_accuracy": perf.get("overall_accuracy"),
            "auto_evaluation_interval_minutes": 30,
            "auto_evaluation_note": "Predictions are evaluated automatically after matches finish.",
        },
        "performance_snapshot": {
            "snapshot_count": perf.get("snapshot_count") or 0,
            "last_updated": perf.get("last_updated"),
            "data_source": perf.get("data_source"),
        },
        "rule_a": {
            "mode": getattr(settings, "rule_a_gate_mode", None) or "active",
            "monitoring_available": True,
        },
        "best_tip_available": best_tips_available,
        "updated_at": _utc_now_iso(),
        "disclaimer": "All counts are from real backend data. Accuracy uses finished matches only.",
    }
