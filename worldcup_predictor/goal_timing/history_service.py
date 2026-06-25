"""API serialization for goal-timing evaluation history (Phase 51E)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.egie.confidence.production_service import HybridConfidenceProductionService
from worldcup_predictor.goal_timing.learning_stats import build_goal_timing_learning_stats
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def serialize_history_row(row: dict[str, Any]) -> dict[str, Any]:
    import json

    display_minute = row.get("display_estimated_first_goal_minute")
    if display_minute is None:
        display_minute = row.get("estimated_first_goal_minute")
    predicted: dict[str, Any] = {
        "first_goal_team": row.get("first_goal_team"),
        "first_goal_time_range": row.get("first_goal_time_range"),
        "estimated_first_goal_minute": _float_or_none(display_minute),
        "confidence_score": _float_or_none(row.get("confidence_score")),
        "model_confidence_score": _float_or_none(row.get("model_confidence_score")),
        "data_quality_score": _float_or_none(row.get("data_quality_score")),
    }
    hybrid = row.get("hybrid_confidence_snapshot")
    if isinstance(hybrid, str):
        try:
            hybrid = json.loads(hybrid)
        except json.JSONDecodeError:
            hybrid = None
    if isinstance(hybrid, dict):
        predicted["hybrid_confidence"] = hybrid

    payload: dict[str, Any] = {
        "evaluation_id": str(row.get("evaluation_id") or row.get("id") or ""),
        "prediction_id": str(row.get("prediction_id") or ""),
        "fixture_id": row.get("fixture_id"),
        "competition_key": row.get("competition_key"),
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "match_date": _iso(row.get("match_date")),
        "predicted": predicted,
        "actual": {
            "first_goal_team": row.get("actual_first_goal_team"),
            "first_goal_minute": row.get("actual_first_goal_minute"),
            "first_goal_time_range": row.get("actual_first_goal_time_range"),
        },
        "status": {
            "first_goal_team": row.get("first_goal_team_status"),
            "goal_range": row.get("time_range_status"),
            "goal_minute": row.get("minute_tolerance_status"),
        },
        "evaluated_at": _iso(row.get("evaluated_at")),
        "model_version": row.get("model_version"),
    }
    if not predicted.get("hybrid_confidence"):
        enriched = HybridConfidenceProductionService.enrich_payload({}, row=row)
        if enriched.get("hybrid_confidence"):
            predicted["hybrid_confidence"] = enriched["hybrid_confidence"]
            payload["hybrid_confidence"] = enriched["hybrid_confidence"]
    else:
        payload["hybrid_confidence"] = predicted["hybrid_confidence"]
    return payload


class GoalTimingHistoryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repository = GoalTimingRepository(self.settings)

    def list_history(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        competition_key: str | None = None,
    ) -> dict[str, Any]:
        rows = self.repository.list_evaluations_joined(
            competition_key=competition_key,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [serialize_history_row(r) for r in rows],
            "count": len(rows),
            "total": self.repository.count_evaluations(competition_key=competition_key),
            "limit": limit,
            "offset": offset,
        }

    def accuracy_summary(self, *, competition_key: str | None = None) -> dict[str, Any]:
        stats = build_goal_timing_learning_stats(
            settings=self.settings,
            competition_key=competition_key,
        )
        markets = stats.get("by_market") or {}
        return {
            "sample_size": stats.get("sample_size", 0),
            "markets": {
                "first_goal_team": markets.get("first_goal_team"),
                "goal_range": markets.get("goal_range"),
                "goal_minute": markets.get("goal_minute"),
            },
            "overall": {
                "first_goal_team_winrate": (markets.get("first_goal_team") or {}).get("winrate"),
                "goal_range_winrate": (markets.get("goal_range") or {}).get("winrate"),
                "goal_minute_winrate": (markets.get("goal_minute") or {}).get("winrate"),
                "goal_minute_soft_winrate": (markets.get("goal_minute") or {}).get("soft_winrate"),
            },
        }

    def performance_report(self, *, competition_key: str | None = None) -> dict[str, Any]:
        return build_goal_timing_learning_stats(
            settings=self.settings,
            competition_key=competition_key,
        )

    def recent_evaluations(self, *, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.repository.list_evaluations_joined(limit=limit, offset=0)
        return [serialize_history_row(r) for r in rows]
