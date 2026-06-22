"""Goal timing feature generation service — build, persist, report."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.goal_timing.data.coverage_report import build_goal_timing_coverage_report
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository


class GoalTimingFeatureService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stored = StoredGoalTimingAdapter(self.settings)
        self.builder = GoalTimingFeatureBuilder(stored=self.stored, max_api_event_fetches=0)
        self.repository = GoalTimingRepository(self.settings)

    def build_features(self, fixture_id: int, *, persist: bool = True) -> dict[str, Any]:
        features = self.builder.build(fixture_id)
        snapshot_id: str | None = None
        if persist:
            snapshot_id = self.repository.save_feature_snapshot(
                fixture_id=int(fixture_id),
                as_of=features.get("as_of") or datetime.now(timezone.utc).isoformat(),
                features=features,
                source_manifest=features.get("provider_manifest") or {},
                competition_key=str(features.get("competition_key") or ""),
            )
        return {
            "fixture_id": fixture_id,
            "feature_snapshot_id": snapshot_id,
            "features": features,
            "data_quality_score": features.get("data_quality_score"),
            "persisted": bool(snapshot_id),
        }

    def coverage_report(self, *, sample_fixture_id: int | None = None) -> dict[str, Any]:
        sample = [sample_fixture_id] if sample_fixture_id else []
        return build_goal_timing_coverage_report(stored=self.stored, sample_fixture_ids=sample)

    def probe_fixture_report(self, fixture_id: int, *, persist: bool = False) -> dict[str, Any]:
        result = self.build_features(fixture_id, persist=persist)
        coverage = self.coverage_report(sample_fixture_id=fixture_id)
        features = result.get("features") or {}
        return {
            "fixture_id": fixture_id,
            "persisted": result.get("persisted"),
            "feature_snapshot_id": result.get("feature_snapshot_id"),
            "data_quality_score": result.get("data_quality_score"),
            "history_samples": features.get("history_samples"),
            "provider_manifest": features.get("provider_manifest"),
            "competition_key": features.get("competition_key"),
            "feature_version": features.get("feature_version"),
            "coverage": coverage,
            "features_preview": {
                "team_goals_scored_by_range": features.get("team_goals_scored_by_range"),
                "first_goal_minute_distribution": features.get("first_goal_minute_distribution"),
                "no_goal_before_minute_probability": features.get("no_goal_before_minute_probability"),
                "league_baseline_timing": features.get("league_baseline_timing"),
            },
        }


def format_probe_report(payload: dict[str, Any]) -> str:
    lines = [
        "=== Goal Timing Feature Probe (Phase 51C) ===",
        f"Fixture: {payload.get('fixture_id')}",
        f"Competition: {payload.get('competition_key')}",
        f"Feature version: {payload.get('feature_version')}",
        f"Data quality: {payload.get('data_quality_score')}",
        f"Persisted: {payload.get('persisted')} ({payload.get('feature_snapshot_id')})",
        "",
        "History samples:",
        json.dumps(payload.get("history_samples") or {}, indent=2),
        "",
        "Provider manifest:",
        json.dumps(payload.get("provider_manifest") or {}, indent=2),
        "",
        "Coverage totals:",
        json.dumps((payload.get("coverage") or {}).get("totals") or {}, indent=2),
        "",
        "League coverage:",
        json.dumps((payload.get("coverage") or {}).get("leagues") or [], indent=2),
        "",
        "Missing gaps:",
        json.dumps((payload.get("coverage") or {}).get("missing_data_gaps") or [], indent=2),
        "",
        "Sportmonks:",
        json.dumps((payload.get("coverage") or {}).get("sportmonks") or {}, indent=2),
    ]
    return "\n".join(lines)
