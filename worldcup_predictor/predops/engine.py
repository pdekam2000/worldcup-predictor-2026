"""PredOps orchestration engine — Phase A15."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.automation.prediction_prefetch.coverage import collect_upcoming_fixtures
from worldcup_predictor.automation.worldcup_background.freshness import _parse_dt
from worldcup_predictor.automation.worldcup_background.prediction_runner import run_and_store_prediction
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.predops.priority import priority_band_for_kickoff, sort_fixtures_by_priority
from worldcup_predictor.predops.refresh_policy import should_enqueue_refresh
from worldcup_predictor.predops.snapshots import create_snapshot_from_payload
from worldcup_predictor.predops.store import PredOpsStore

logger = logging.getLogger(__name__)

PREDOPS_COMPETITIONS: tuple[str, ...] = (
    "world_cup_2026",
    "champions_league",
    "europa_league",
    "conference_league",
    "premier_league",
    "la_liga",
    "serie_a",
    "bundesliga",
    "ligue_1",
)


@dataclass
class PredOpsCycleResult:
    enqueued: int = 0
    processed: int = 0
    snapshots_created: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = False
    max_jobs: int = 0
    elapsed_ms: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)


def _load_stored_payload(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any] | None:
    row = repo.get_worldcup_stored_prediction(fixture_id, include_inactive=True)
    if not row or not row.get("payload_json"):
        return None
    try:
        return json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None


def sync_queue_from_fixtures(
    store: PredOpsStore,
    fixtures: list[dict[str, Any]],
    *,
    force: bool = False,
) -> int:
    enqueued = 0
    for fx in fixtures:
        fid = int(fx["fixture_id"])
        ck = str(fx["competition_key"])
        kick = _parse_dt(fx.get("kickoff_utc"))
        snap = store.get_latest_snapshot(fid)
        payload = (snap or {}).get("payload")
        if not payload:
            payload = _load_stored_payload(
                FootballIntelligenceRepository(store.settings.sqlite_path or None), fid
            )
        do, reason = should_enqueue_refresh(
            has_snapshot=snap is not None,
            payload=payload,
            last_generated_at=(snap or {}).get("generated_at"),
            kickoff_utc=kick,
            force=force,
        )
        if not do:
            continue
        band = priority_band_for_kickoff(kick)
        ok, _ = store.enqueue_job(
            fixture_id=fid,
            competition_key=ck,
            kickoff_utc=fx.get("kickoff_utc"),
            priority_band=band,
            trigger_reason=reason,
        )
        if ok:
            enqueued += 1
    return enqueued


def run_predops_cycle(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    max_jobs: int | None = None,
    competition_keys: list[str] | None = None,
    dry_run: bool = False,
    force_enqueue: bool = False,
    locale: str = "en",
) -> PredOpsCycleResult:
    settings = settings or get_settings()
    window_days = window_days if window_days is not None else getattr(
        settings, "prediction_prefetch_window_days", 7
    )
    max_jobs = max_jobs if max_jobs is not None else getattr(
        settings, "predops_max_jobs_per_cycle", getattr(settings, "prediction_prefetch_max_per_cycle", 24)
    )
    throttle = float(getattr(settings, "api_throttle_delay_seconds", 1.0) or 1.0)
    keys = set(competition_keys or PREDOPS_COMPETITIONS)

    started = time.perf_counter()
    store = PredOpsStore(settings)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    result = PredOpsCycleResult(dry_run=dry_run, max_jobs=max_jobs)

    fixtures = [
        f
        for f in collect_upcoming_fixtures(settings=settings, window_days=window_days)
        if f["competition_key"] in keys
    ]
    fixtures = sort_fixtures_by_priority(fixtures)

    result.enqueued = sync_queue_from_fixtures(store, fixtures, force=force_enqueue)
    if dry_run:
        result.skipped = len(fixtures)
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        return result

    jobs = store.claim_next_jobs(limit=max_jobs)
    for job in jobs:
        fid = int(job["fixture_id"])
        ck = str(job["competition_key"])
        trigger = str(job.get("trigger_reason") or "queue")
        try:
            t0 = time.perf_counter()
            payload = run_and_store_prediction(
                fid,
                settings=settings,
                competition_key=ck,
                locale=locale,
                record_history=False,
                source="predops_a15",
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            if payload.get("status") == "ok":
                snap_id = create_snapshot_from_payload(
                    store,
                    fixture_id=fid,
                    competition_key=ck,
                    kickoff_utc=job.get("kickoff_utc"),
                    payload=payload,
                    trigger_reason=trigger,
                )
                store.complete_job(int(job["id"]))
                result.processed += 1
                result.snapshots_created += 1
                result.details.append(
                    {
                        "fixture_id": fid,
                        "action": "snapshot",
                        "snapshot_id": snap_id,
                        "latency_ms": latency_ms,
                        "coverage_state": "no_bet" if payload.get("no_bet") else "completed",
                    }
                )
            else:
                store.fail_job(int(job["id"]), reason=str(payload.get("message") or "pipeline_error"))
                result.errors += 1
            if throttle > 0:
                time.sleep(throttle)
        except Exception as exc:
            logger.exception("PredOps job failed fixture %s", fid)
            store.fail_job(int(job["id"]), reason=str(exc))
            result.errors += 1

    result.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return result


def backfill_snapshots_from_stored(
    *,
    settings: Settings | None = None,
    competition_keys: list[str] | None = None,
    limit: int = 500,
) -> int:
    """Create predops snapshots from existing stored predictions (no pipeline rerun)."""
    settings = settings or get_settings()
    store = PredOpsStore(settings)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    keys = competition_keys or list(PREDOPS_COMPETITIONS)
    created = 0
    for key in keys:
        rows = repo.list_worldcup_stored_predictions(competition_key=key, limit=limit, offset=0)
        for row in rows:
            fid = row.get("fixture_id")
            if fid is None:
                continue
            fid = int(fid)
            if store.get_latest_snapshot(fid):
                continue
            try:
                payload = json.loads(row["payload_json"]) if isinstance(row.get("payload_json"), str) else row.get("payload_json")
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                continue
            create_snapshot_from_payload(
                store,
                fixture_id=fid,
                competition_key=key,
                kickoff_utc=row.get("kickoff_utc"),
                payload=payload,
                trigger_reason="backfill_stored",
            )
            created += 1
    return created
