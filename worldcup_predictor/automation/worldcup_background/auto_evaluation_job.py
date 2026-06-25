"""Phase 44A — production auto evaluation entry point for systemd timer."""

from __future__ import annotations

import logging
import sys
from typing import Any

from worldcup_predictor.automation.worldcup_background.evaluation_trust import run_evaluation_quarantine_pass
from worldcup_predictor.automation.worldcup_background.result_evaluation_job import (
    EvaluationJobResult,
    run_evaluate_worldcup_results,
)
from worldcup_predictor.automation.worldcup_background.result_refresh import refresh_stored_prediction_results
from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def configure_auto_evaluation_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def run_production_auto_evaluation(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int | None = None,
) -> EvaluationJobResult:
    """Run stored-first evaluation — safe for periodic systemd execution."""
    configure_auto_evaluation_logging()
    settings = settings or get_settings()

    logger.info(
        "worldcup_auto_evaluation_start competition_key=%s mode=stored_first",
        competition_key,
    )
    refresh = refresh_stored_prediction_results(
        settings=settings,
        competition_key=competition_key,
        limit=limit,
    )
    logger.info(
        "worldcup_result_refresh_done fixtures_updated=%d results_updated=%d api_fetches=%d errors=%d",
        refresh.fixtures_updated,
        refresh.results_updated,
        refresh.api_fetches,
        refresh.errors,
    )
    quarantine = run_evaluation_quarantine_pass(settings=settings, competition_key=competition_key)
    if quarantine.quarantined:
        logger.info("worldcup_quarantine_pass quarantined=%d", quarantine.quarantined)
    result = run_evaluate_worldcup_results(
        settings=settings,
        competition_key=competition_key,
        limit=limit,
        mode="stored_first",
        skip_unchanged=True,
        rebuild_summary=True,
    )
    logger.info(
        "worldcup_auto_evaluation_done competition_key=%s evaluated=%d updated=%d skipped=%d errors=%d",
        competition_key,
        result.evaluated,
        result.updated,
        result.skipped,
        result.errors,
    )
    return result


def auto_evaluation_exit_code(result: EvaluationJobResult) -> int:
    return 1 if result.errors > 0 else 0


def auto_evaluation_summary_dict(result: EvaluationJobResult) -> dict[str, Any]:
    return result.to_log_dict()
