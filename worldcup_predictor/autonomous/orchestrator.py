"""Autonomous platform orchestrator — Phase 61."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from worldcup_predictor.autonomous.completion_detector import detect_completed_fixtures
from worldcup_predictor.autonomous.evaluation_engine import run_autonomous_evaluations
from worldcup_predictor.autonomous.fixture_discovery import discover_upcoming_fixtures
from worldcup_predictor.autonomous.performance_certification import run_performance_certification
from worldcup_predictor.autonomous.prediction_scheduler import run_autonomous_predictions
from worldcup_predictor.autonomous.research_integration import merge_into_highlights_payload
from worldcup_predictor.autonomous.store import AutonomousStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.research.highlights_service import cache_highlights_payload, load_highlights_payload

logger = logging.getLogger(__name__)


def run_autonomous_cycle(
    *,
    settings: Settings | None = None,
    fixture_limit: int | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    if not settings.autonomous_platform_enabled:
        return {"status": "disabled", "reason": "AUTONOMOUS_PLATFORM_ENABLED=false"}

    if dry_run is not None:
        settings = settings.model_copy(update={"autonomous_dry_run": dry_run})

    store = AutonomousStore(settings)
    cycle_id = store.start_cycle_run()
    started = time.time()
    api_calls = 0

    try:
        discovery = discover_upcoming_fixtures(
            settings=settings,
            limit_per_competition=settings.autonomous_fixture_limit_per_cycle,
        )
        api_calls += discovery.api_calls_used

        fixtures = discovery.fixtures[: (fixture_limit or settings.autonomous_fixture_limit_per_cycle)]
        predict_result = run_autonomous_predictions(fixtures, settings=settings)
        api_calls += predict_result.api_calls_used

        completion = detect_completed_fixtures(settings=settings, limit=200)
        api_calls += completion.api_calls_used

        eval_result = run_autonomous_evaluations(settings=settings, limit=500)
        api_calls += eval_result.api_calls_used

        certification = run_performance_certification(settings=settings)

        try:
            highlights = load_highlights_payload()
            merged = merge_into_highlights_payload(highlights, settings=settings)
            cache_highlights_payload(merged)
        except Exception as exc:
            logger.warning("research_highlights_merge_failed: %s", exc)

        report: dict[str, Any] = {
            "status": "ok",
            "phase": "61",
            "cycle_id": cycle_id,
            "duration_seconds": round(time.time() - started, 2),
            "api_calls_used": api_calls,
            "discovery": discovery.to_dict(),
            "predictions": predict_result.to_dict(),
            "completion": completion.to_dict(),
            "evaluation": eval_result.to_dict(),
            "certification": certification.to_dict(),
        }

        artifacts = Path("artifacts/phase61_autonomous")
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "latest_cycle_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        store.finish_cycle_run(cycle_id, status="ok", report=report)
        return report
    except Exception as exc:
        logger.exception("autonomous_cycle_failed")
        fail_report = {"status": "error", "error": str(exc), "cycle_id": cycle_id}
        store.finish_cycle_run(cycle_id, status="error", report=fail_report)
        return fail_report


def run_autonomous_scheduler_loop(
    *,
    settings: Settings | None = None,
    interval_seconds: int = 3600,
    max_iterations: int | None = None,
) -> None:
    settings = settings or get_settings()
    iteration = 0
    while True:
        iteration += 1
        logger.info("autonomous_scheduler iteration=%s", iteration)
        run_autonomous_cycle(settings=settings)
        if max_iterations is not None and iteration >= max_iterations:
            break
        time.sleep(interval_seconds)
