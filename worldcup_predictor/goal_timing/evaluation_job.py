"""Automatic goal-timing evaluation after match finish (Phase 51E)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.goal_timing.evaluation import evaluate_goal_timing_prediction
from worldcup_predictor.goal_timing.outcome_adapter import build_evaluation_actuals
from worldcup_predictor.goal_timing.result_refresh import refresh_goal_timing_fixture_results
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository

logger = logging.getLogger(__name__)


@dataclass
class GoalTimingEvaluationJobResult:
    refresh: dict[str, Any] = field(default_factory=dict)
    scanned: int = 0
    evaluated: int = 0
    updated: int = 0
    skipped_not_finished: int = 0
    skipped_no_actuals: int = 0
    skipped_unchanged: int = 0
    pending: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "refresh": self.refresh,
            "scanned": self.scanned,
            "evaluated": self.evaluated,
            "updated": self.updated,
            "skipped_not_finished": self.skipped_not_finished,
            "skipped_no_actuals": self.skipped_no_actuals,
            "skipped_unchanged": self.skipped_unchanged,
            "pending": self.pending,
            "errors": self.errors,
            "details": self.details[:50],
        }


def _status_tuple(row: dict[str, Any] | None) -> tuple[str, str, str]:
    if not row:
        return ("pending", "pending", "pending")
    return (
        str(row.get("first_goal_team_status") or "pending"),
        str(row.get("time_range_status") or "pending"),
        str(row.get("minute_tolerance_status") or "pending"),
    )


def run_goal_timing_evaluations(
    *,
    settings: Settings | None = None,
    limit: int | None = 200,
    skip_unchanged: bool = True,
    refresh_first: bool = True,
    max_api_calls: int = 50,
) -> GoalTimingEvaluationJobResult:
    settings = settings or get_settings()
    result = GoalTimingEvaluationJobResult()

    if refresh_first:
        refresh_outcome = refresh_goal_timing_fixture_results(
            settings=settings,
            limit=limit,
            max_api_calls=max_api_calls,
        )
        result.refresh = {
            "scanned": refresh_outcome.scanned,
            "api_fetches": refresh_outcome.api_fetches,
            "fixtures_updated": refresh_outcome.fixtures_updated,
            "results_updated": refresh_outcome.results_updated,
            "outcomes_persisted": refresh_outcome.outcomes_persisted,
            "errors": refresh_outcome.errors,
        }

    gt_repo = GoalTimingRepository(settings)
    resolver = FixtureOutcomeResolver(settings)
    predictions = gt_repo.list_published_predictions(limit=limit or 500)
    result.scanned = len(predictions)

    for pred in predictions:
        fixture_id = int(pred["fixture_id"])
        prediction_id = str(pred["id"])
        try:
            outcome = resolver.resolve(fixture_id)
            if not outcome.is_finished:
                result.skipped_not_finished += 1
                continue

            actuals = build_evaluation_actuals(
                outcome,
                home_team=str(pred.get("home_team") or ""),
                away_team=str(pred.get("away_team") or ""),
            )
            if actuals["actual_first_goal_team"] is None and actuals["actual_first_goal_minute"] is None:
                if str(actuals.get("final_score") or "").strip() not in {"", "0-0", "0:0"}:
                    result.skipped_no_actuals += 1
                    result.details.append({"fixture_id": fixture_id, "status": "skipped_no_actuals"})
                    continue

            eval_result = evaluate_goal_timing_prediction(
                fixture_id=fixture_id,
                prediction_id=prediction_id,
                predicted_first_goal_team=str(pred.get("first_goal_team") or ""),
                predicted_first_goal_time_range=str(pred.get("first_goal_time_range") or ""),
                estimated_first_goal_minute=float(pred["display_estimated_first_goal_minute"])
                if pred.get("display_estimated_first_goal_minute") is not None
                else pred.get("estimated_first_goal_minute"),
                actual_first_goal_team=actuals["actual_first_goal_team"],
                actual_first_goal_minute=actuals["actual_first_goal_minute"],
            )

            existing = gt_repo.get_evaluation_by_prediction_id(prediction_id)
            if skip_unchanged and existing:
                if _status_tuple(existing) == (
                    eval_result.first_goal_team_status,
                    eval_result.time_range_status,
                    eval_result.minute_tolerance_status,
                ):
                    result.skipped_unchanged += 1
                    continue

            gt_repo.save_evaluation(eval_result)
            if existing:
                result.updated += 1
            else:
                result.evaluated += 1

            if any(
                s == "pending"
                for s in (
                    eval_result.first_goal_team_status,
                    eval_result.time_range_status,
                    eval_result.minute_tolerance_status,
                )
            ):
                result.pending += 1

            result.details.append(
                {
                    "fixture_id": fixture_id,
                    "prediction_id": prediction_id,
                    "first_goal_team_status": eval_result.first_goal_team_status,
                    "time_range_status": eval_result.time_range_status,
                    "minute_tolerance_status": eval_result.minute_tolerance_status,
                }
            )
        except Exception as exc:
            logger.exception("Goal timing evaluation failed fixture_id=%s", fixture_id)
            result.errors += 1
            result.details.append({"fixture_id": fixture_id, "status": "error", "reason": str(exc)})

    logger.info(
        "goal_timing_evaluation_pass scanned=%d evaluated=%d updated=%d skipped_not_finished=%d "
        "skipped_no_actuals=%d skipped_unchanged=%d pending=%d errors=%d",
        result.scanned,
        result.evaluated,
        result.updated,
        result.skipped_not_finished,
        result.skipped_no_actuals,
        result.skipped_unchanged,
        result.pending,
        result.errors,
    )
    return result


def run_goal_timing_learning_loop(
    *,
    settings: Settings | None = None,
    limit: int | None = 200,
    max_api_calls: int = 50,
) -> dict[str, Any]:
    """Full Phase 51E loop: refresh finished fixtures → evaluate → return stats."""
    settings = settings or get_settings()
    from worldcup_predictor.goal_timing.learning_stats import build_goal_timing_learning_stats

    job = run_goal_timing_evaluations(
        settings=settings,
        limit=limit,
        refresh_first=True,
        max_api_calls=max_api_calls,
    )
    stats = build_goal_timing_learning_stats(settings=settings)
    return {
        "job": job.to_dict(),
        "learning_stats": stats,
    }
