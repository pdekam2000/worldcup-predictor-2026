"""EGIE monitoring dashboard aggregation (Phase 51G)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.goal_timing.history_service import GoalTimingHistoryService
from worldcup_predictor.goal_timing.learning_stats import build_goal_timing_learning_stats
from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService
from worldcup_predictor.goal_timing.scheduler_state import load_scheduler_state, probe_systemd_timer
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100, 1)


def _bucket_winrates(buckets: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not buckets:
        return []
    rows: list[dict[str, Any]] = []
    for key, stats in sorted(buckets.items()):
        if not isinstance(stats, dict):
            continue
        rows.append(
            {
                "bucket": key,
                "winrate": stats.get("winrate"),
                "winrate_pct": _pct(stats.get("winrate")),
                "correct": stats.get("correct", 0),
                "wrong": stats.get("wrong", 0),
                "total": stats.get("total", 0),
            }
        )
    return rows


class GoalTimingDashboardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repository = GoalTimingRepository(self.settings)
        self.history = GoalTimingHistoryService(self.settings)
        self.predictions = GoalTimingPredictionService(self.settings)

    def build_monitoring_dashboard(self) -> dict[str, Any]:
        stats = self.repository.prediction_monitoring_counts()
        accuracy = self.history.accuracy_summary()
        performance = build_goal_timing_learning_stats(settings=self.settings)
        scheduler_file = load_scheduler_state(self.settings)
        timer = probe_systemd_timer()

        published = int(stats.get("published_picks") or 0)
        evaluated = int(stats.get("evaluated_picks") or 0)
        no_pick = int(stats.get("no_pick_count") or 0)
        pending = max(0, published - evaluated)

        stored_picks = self.predictions.list_stored_picks(limit=50, upcoming_only=True)
        no_pick_rows = self.repository.list_no_pick_predictions(limit=20)

        markets = accuracy.get("markets") or {}
        overall = accuracy.get("overall") or {}

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "52E",
            "counts": {
                "published_picks": published,
                "evaluated_picks": evaluated,
                "pending_picks": pending,
                "no_pick_count": no_pick,
                "upcoming_picks": len(stored_picks.get("picks") or []),
            },
            "accuracy": {
                "sample_size": accuracy.get("sample_size", 0),
                "team_winrate": overall.get("first_goal_team_winrate"),
                "team_winrate_pct": _pct(overall.get("first_goal_team_winrate")),
                "range_winrate": overall.get("goal_range_winrate"),
                "range_winrate_pct": _pct(overall.get("goal_range_winrate")),
                "minute_winrate": overall.get("goal_minute_winrate"),
                "minute_winrate_pct": _pct(overall.get("goal_minute_winrate")),
                "minute_soft_winrate": overall.get("goal_minute_soft_winrate"),
                "minute_soft_winrate_pct": _pct(overall.get("goal_minute_soft_winrate")),
                "markets": markets,
            },
            "learning": {
                "dq_bucket_winrate": _bucket_winrates(
                    (performance.get("by_dq_bucket") or {}).get("first_goal_team")
                ),
                "confidence_bucket_winrate": _bucket_winrates(
                    (performance.get("by_confidence_bucket") or {}).get("first_goal_team")
                ),
            },
            "scheduler": {
                **timer,
                "last_run_at": scheduler_file.get("last_run_at"),
                "last_refresh_at": scheduler_file.get("last_refresh_at"),
                "last_api_calls": scheduler_file.get("last_api_calls", 0),
                "last_job": scheduler_file.get("last_job") or {},
                "last_refresh": scheduler_file.get("last_refresh") or {},
            },
            "no_pick": {
                "count": no_pick,
                "items": [
                    {
                        "fixture_id": row.get("fixture_id"),
                        "home_team": row.get("home_team"),
                        "away_team": row.get("away_team"),
                        "match_date": row.get("match_date").isoformat()
                        if row.get("match_date") and hasattr(row["match_date"], "isoformat")
                        else row.get("match_date"),
                        "data_quality_score": float(row.get("data_quality_score") or 0),
                        "reason": _no_pick_reason(row),
                    }
                    for row in no_pick_rows
                ],
            },
            "upcoming_picks": stored_picks.get("picks") or [],
            "recent_evaluations": self.history.recent_evaluations(limit=8),
            "data_source": "postgresql_sqlite_live",
            "postgres_available": bool(stats.get("total_predictions", 0) or stored_picks.get("picks")),
        }


def _no_pick_reason(row: dict[str, Any]) -> str:
    explanation = str(row.get("explanation") or "").strip()
    if explanation:
        return explanation
    dq = float(row.get("data_quality_score") or 0)
    if dq < 0.45:
        return "Data quality below prediction threshold (DQ < 0.45)"
    return "NO_PICK — insufficient signal for published pick"
