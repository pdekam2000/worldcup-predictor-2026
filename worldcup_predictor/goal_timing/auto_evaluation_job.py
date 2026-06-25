"""Phase 51F — production auto evaluation entry point for systemd timer."""

from __future__ import annotations

import logging
import sys
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.goal_timing.evaluation_job import (
    GoalTimingEvaluationJobResult,
    run_goal_timing_learning_loop,
)

logger = logging.getLogger(__name__)


def configure_egie_evaluation_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def run_production_egie_goal_timing_evaluation(
    *,
    settings: Settings | None = None,
    limit: int = 200,
    max_api_calls: int = 50,
) -> dict[str, Any]:
    """Run EGIE evaluation loop — safe for periodic systemd execution."""
    configure_egie_evaluation_logging()
    settings = settings or get_settings()

    logger.info("egie_goal_timing_evaluation_start limit=%d max_api_calls=%d", limit, max_api_calls)
    payload = run_goal_timing_learning_loop(
        settings=settings,
        limit=limit,
        max_api_calls=max_api_calls,
    )
    job = payload.get("job") or {}
    refresh = job.get("refresh") or {}
    stats = payload.get("learning_stats") or {}

    logger.info(
        "egie_goal_timing_refresh_done scanned=%d api_fetches=%d fixtures_updated=%d "
        "results_updated=%d outcomes_persisted=%d errors=%d",
        refresh.get("scanned", 0),
        refresh.get("api_fetches", 0),
        refresh.get("fixtures_updated", 0),
        refresh.get("results_updated", 0),
        refresh.get("outcomes_persisted", 0),
        refresh.get("errors", 0),
    )
    logger.info(
        "egie_goal_timing_evaluation_done scanned_picks=%d evaluated=%d updated=%d "
        "skipped_not_finished=%d skipped_no_actuals=%d skipped_unchanged=%d pending=%d errors=%d",
        job.get("scanned", 0),
        job.get("evaluated", 0),
        job.get("updated", 0),
        job.get("skipped_not_finished", 0),
        job.get("skipped_no_actuals", 0),
        job.get("skipped_unchanged", 0),
        job.get("pending", 0),
        job.get("errors", 0),
    )
    logger.info(
        "egie_goal_timing_learning_stats sample_size=%d",
        stats.get("sample_size", 0),
    )
    from worldcup_predictor.goal_timing.scheduler_state import record_scheduler_run

    record_scheduler_run(payload, settings=settings)
    return payload


def egie_evaluation_exit_code(job: GoalTimingEvaluationJobResult | dict[str, Any]) -> int:
    if isinstance(job, dict):
        errors = int((job.get("job") or {}).get("errors", 0) or 0)
        refresh_errors = int(((job.get("job") or {}).get("refresh") or {}).get("errors", 0) or 0)
        return 1 if errors + refresh_errors > 0 else 0
    return 1 if job.errors > 0 else 0
