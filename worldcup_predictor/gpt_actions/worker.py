"""Background prediction job worker (async semantics, single heavy job)."""

from __future__ import annotations

import threading
from typing import Any

from worldcup_predictor.gpt_actions.config import GptActionsConfig
from worldcup_predictor.gpt_actions.delegation import (
    filter_matches_by_odds,
    format_fixture_evidence,
    rank_best_matches,
    run_predictions_for_fixtures,
)
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.policies import validate_fixture_id_list
from worldcup_predictor.mcp_server import runtime as mcp_runtime


def _resolve_fixture_ids(request: dict[str, Any], *, max_count: int) -> list[int]:
    explicit = request.get("fixture_ids") or []
    if explicit:
        return validate_fixture_id_list(list(explicit), max_count=max_count)

    filtered = filter_matches_by_odds(
        target_date=str(request["date"]),
        timezone=str(request.get("timezone") or "Europe/Vienna"),
        home_odds_gt=(request.get("filter") or {}).get("home_odds_gt"),
        away_odds_gt=(request.get("filter") or {}).get("away_odds_gt"),
    )
    ids = [int(m["fixture_id"]) for m in filtered.get("matches") or []]
    return ids[:max_count]


def _aggregate_status(predictions: list[dict[str, Any]]) -> str:
    if not predictions:
        return "failed"
    statuses = {str(p.get("quality") or "unknown") for p in predictions}
    if statuses == {"OK"}:
        return "completed"
    if "OK" in statuses or "PARTIAL" in statuses:
        return "partial"
    return "failed"


def execute_prediction_job(
    job_id: str,
    *,
    store: JobStore,
    config: GptActionsConfig,
) -> None:
    record = store.get(job_id)
    if not record:
        return
    store.update(job_id, status="running")
    request = record.get("request") or {}
    try:
        fixture_ids = _resolve_fixture_ids(request, max_count=config.max_fixture_ids_per_job)
        if not fixture_ids:
            store.update(
                job_id,
                status="failed",
                error="no_fixtures_matched_filter",
                result={"fixture_count": 0, "predictions": [], "all_match_ranking": [], "best_3": []},
            )
            return

        timezone = str(request.get("timezone") or "Europe/Vienna")
        refresh = bool(request.get("refresh_if_stale", True))
        select_best = int(request.get("select_best") or 3)
        include_all = bool(request.get("include_all_predictions", True))

        predictions: list[dict[str, Any]] = []
        for fixture_id in fixture_ids:
            raw = mcp_runtime.run_fixture_prediction(int(fixture_id), refresh_if_stale=refresh)
            predictions.append(format_fixture_evidence(raw, timezone=timezone))

        ranking = rank_best_matches(predictions, select_best=select_best)
        result = {
            "date": request.get("date"),
            "timezone": timezone,
            "fixture_count": len(fixture_ids),
            "fixture_ids": fixture_ids,
            "predictions": predictions if include_all else [],
            "all_match_ranking": ranking["all_match_ranking"],
            "best_3": ranking["best_3"][: min(3, select_best)],
        }
        status = _aggregate_status(predictions)
        store.update(job_id, status=status, result=result)
    except Exception as exc:
        store.update(job_id, status="failed", error=str(exc)[:500])
    finally:
        store.release_active(job_id)


def enqueue_prediction_job(
    job_id: str,
    *,
    store: JobStore,
    config: GptActionsConfig,
) -> None:
    thread = threading.Thread(
        target=execute_prediction_job,
        kwargs={"job_id": job_id, "store": store, "config": config},
        name=f"gpt-actions-job-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
