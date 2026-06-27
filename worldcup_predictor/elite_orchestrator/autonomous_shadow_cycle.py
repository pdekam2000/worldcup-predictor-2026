"""Phase A22 — autonomous Elite Shadow cycle (predict → evaluate → root cause)."""

from __future__ import annotations

import time
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.elite_orchestrator.fixture_selector import select_fixtures_by_ids, select_upcoming_fixtures
from worldcup_predictor.elite_orchestrator.pairing import pair_predictions
from worldcup_predictor.elite_orchestrator.shadow_config import EVALUATIONS_PATH, PREDICTIONS_PATH
from worldcup_predictor.elite_orchestrator.shadow_health import mark_run_failure, mark_run_start, mark_run_success
from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import count_jsonl_lines
from worldcup_predictor.elite_orchestrator.shadow_queue import load_queue, mark_queue_processed, queue_pending_count
from worldcup_predictor.elite_orchestrator.shadow_runtime import run_shadow_for_fixtures
from worldcup_predictor.elite_orchestrator.shadow_store import append_predictions, validate_row
from worldcup_predictor.root_cause.config import STORE_DIR
from worldcup_predictor.root_cause.runner import run_phase58d


def _run_shadow_for_fixture_list(fixtures: list[dict[str, Any]], *, force: bool = False) -> dict[str, Any]:
    rows = run_shadow_for_fixtures(fixtures) if fixtures else []
    validation_errors: list[str] = []
    for row in rows[:5]:
        validation_errors.extend(validate_row(row))
    write_result = {"written": 0, "skipped_duplicates": 0}
    if rows:
        write_result = append_predictions(rows, force=force)
    return {
        "fixtures": len(fixtures),
        "predictions_generated": len(rows),
        "write_result": write_result,
        "validation_errors": validation_errors,
    }


def run_autonomous_shadow_cycle(
    *,
    settings: Settings | None = None,
    days_ahead: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
    skip_root_cause: bool = False,
    trigger: str = "scheduler",
) -> dict[str, Any]:
    """Full shadow-only cycle. Never touches production prediction pipeline."""
    settings = settings or get_settings()
    if not settings.elite_shadow_scheduler_enabled and trigger == "scheduler":
        return {"status": "disabled", "reason": "ELITE_SHADOW_SCHEDULER_ENABLED=false"}

    started = time.time()
    mark_run_start(scheduler_enabled=settings.elite_shadow_scheduler_enabled)

    try:
        rc_before = count_jsonl_lines(STORE_DIR / "knowledge_records.jsonl")

        fixtures = select_upcoming_fixtures(
            days_ahead=days_ahead or settings.elite_shadow_days_ahead,
            limit=limit or settings.elite_shadow_fixture_limit,
        )

        queue_rows = load_queue(limit=settings.elite_shadow_queue_batch_size)
        queue_ids = [int(r["fixture_id"]) for r in queue_rows if r.get("fixture_id")]
        if queue_ids:
            queued_fixtures = select_fixtures_by_ids(queue_ids)
            seen = {int(f["fixture_id"]) for f in fixtures}
            for fx in queued_fixtures:
                if int(fx["fixture_id"]) not in seen:
                    fixtures.append(fx)

        shadow_result = {"fixtures": 0, "predictions_generated": 0, "write_result": {}}
        pair_result: dict[str, Any] = {}
        root_cause: dict[str, Any] = {"status": "skipped"}

        if not dry_run:
            shadow_result = _run_shadow_for_fixture_list(fixtures, force=force)
            pair_result = pair_predictions(force=force)
            if queue_ids:
                mark_queue_processed(queue_ids)
            if not skip_root_cause:
                root_cause = run_phase58d(historical_limit=settings.elite_shadow_root_cause_limit, force_store=False)

        rc_after = count_jsonl_lines(STORE_DIR / "knowledge_records.jsonl")
        report: dict[str, Any] = {
            "status": "ok",
            "phase": "A22",
            "trigger": trigger,
            "dry_run": dry_run,
            "force": force,
            "fixtures_selected": len(fixtures),
            "predictions_generated": shadow_result.get("predictions_generated", 0),
            "write_result": shadow_result.get("write_result", {}),
            "pair_result": pair_result,
            "root_cause": {
                **(root_cause if isinstance(root_cause, dict) else {}),
                "records_added": max(0, rc_after - rc_before),
            },
            "queue_pending": queue_pending_count(),
            "production_changes": False,
            "jsonl_paths": {
                "predictions": str(PREDICTIONS_PATH),
                "evaluations": str(EVALUATIONS_PATH),
                "root_cause": str(STORE_DIR / "knowledge_records.jsonl"),
            },
        }

        mark_run_success(
            report,
            duration_seconds=time.time() - started,
            interval_hours=settings.elite_shadow_interval_hours,
        )
        return report
    except Exception as exc:
        mark_run_failure(str(exc))
        return {"status": "error", "error": str(exc), "phase": "A22", "trigger": trigger}


def run_shadow_scheduler_loop(
    *,
    settings: Settings | None = None,
    interval_seconds: int | None = None,
    max_iterations: int | None = None,
) -> None:
    import time as _time

    settings = settings or get_settings()
    interval = interval_seconds or int(settings.elite_shadow_interval_hours * 3600)
    iteration = 0
    while True:
        iteration += 1
        run_autonomous_shadow_cycle(settings=settings, trigger="scheduler")
        if max_iterations is not None and iteration >= max_iterations:
            break
        _time.sleep(interval)
