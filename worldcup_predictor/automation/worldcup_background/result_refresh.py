"""Phase 45B / 46C-1 — refresh fixture results + persist outcome detail for stored predictions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.outcomes.outcome_persistence import (
    build_parsed_outcome,
    needs_outcome_backfill,
    persist_fixture_outcome,
    should_fetch_events_for_fixture,
)
from worldcup_predictor.results.match_results_store import MatchResultsStore, save_finished_fixtures
from worldcup_predictor.schedule.match_center import classify_status

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _kickoff_passed(row: dict[str, Any], *, now_iso: str) -> bool:
    kickoff = row.get("kickoff_utc")
    if not kickoff:
        payload_raw = row.get("payload_json")
        if payload_raw:
            try:
                payload = json.loads(payload_raw)
                kickoff = payload.get("kickoff_utc") if isinstance(payload, dict) else None
            except (json.JSONDecodeError, TypeError):
                kickoff = None
    if not kickoff:
        return False
    return str(kickoff) <= now_iso


def _events_from_fixture_item(item: dict[str, Any]) -> list[Any]:
    embedded = item.get("events")
    if isinstance(embedded, list) and embedded:
        return embedded
    return []


def _sync_outcome_for_fixture(
    *,
    repo: FootballIntelligenceRepository,
    api: ApiFootballClient,
    fixture_id: int,
    item: dict[str, Any],
    fixture: Any,
    competition_key: str,
    outcome: ResultRefreshOutcome,
) -> None:
    if not should_fetch_events_for_fixture(fixture):
        return

    result_row = repo.get_fixture_result_row(fixture_id)
    if not result_row:
        return

    event_count = repo.count_fixture_goal_events(fixture_id)
    if not needs_outcome_backfill(result_row, goal_event_count=event_count):
        outcome.outcomes_skipped_complete += 1
        return

    events_raw = _events_from_fixture_item(item)
    if not events_raw:
        try:
            call = api.get_fixture_events(fixture_id)
            outcome.api_event_fetches += 1
            if call.ok and isinstance(call.data, list):
                events_raw = call.data
        except Exception:
            logger.exception("Event fetch failed fixture_id=%s", fixture_id)

    parsed = build_parsed_outcome(
        fixture,
        events_raw,
        outcome_source=str(getattr(fixture, "source", None) or "api-football"),
    )
    if persist_fixture_outcome(repo, parsed, competition_key=competition_key):
        outcome.outcomes_persisted += 1
        outcome.details.append(
            {
                "fixture_id": fixture_id,
                "status": "outcome_persisted",
                "ht_score": parsed.ht_score,
                "first_goal_minute": parsed.first_goal_minute,
                "goal_events": len(parsed.goal_events),
            }
        )


@dataclass
class ResultRefreshOutcome:
    scanned: int = 0
    api_fetches: int = 0
    api_event_fetches: int = 0
    fixtures_updated: int = 0
    results_updated: int = 0
    outcomes_persisted: int = 0
    outcomes_skipped_complete: int = 0
    jsonl_saved: int = 0
    skipped_already_finished: int = 0
    skipped_not_due: int = 0
    skipped_no_api: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


def refresh_stored_prediction_results(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int | None = None,
    dry_run: bool = False,
    force_outcome_sync: bool = False,
) -> ResultRefreshOutcome:
    """Fetch latest fixture status/results and persist outcome detail for stored predictions past kickoff."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    resolver = FixtureOutcomeResolver(settings)
    api = ApiFootballClient(settings)
    outcome = ResultRefreshOutcome()
    now_iso = _utc_now_iso()

    stored_rows = repo.list_worldcup_stored_prediction_rows(competition_key=competition_key)
    due_rows = [r for r in stored_rows if _kickoff_passed(r, now_iso=now_iso)]
    outcome.skipped_not_due = len(stored_rows) - len(due_rows)
    if limit is not None:
        due_rows = due_rows[: max(0, int(limit))]
    outcome.scanned = len(due_rows)

    finished_for_jsonl: list[Any] = []

    try:
        for row in due_rows:
            fixture_id = int(row["fixture_id"])
            existing = resolver.resolve(fixture_id)
            result_row = repo.get_fixture_result_row(fixture_id)
            event_count = repo.count_fixture_goal_events(fixture_id)
            outcome_incomplete = force_outcome_sync or needs_outcome_backfill(
                result_row,
                goal_event_count=event_count,
            )
            if existing.is_finished and existing.final_score and not outcome_incomplete:
                outcome.skipped_already_finished += 1
                continue

            if not api.is_configured:
                outcome.skipped_no_api += 1
                outcome.details.append({"fixture_id": fixture_id, "status": "skipped_no_api"})
                continue

            try:
                call = api.get_fixture_by_id(fixture_id)
                outcome.api_fetches += 1
                if not call.data:
                    outcome.details.append({"fixture_id": fixture_id, "status": "no_data"})
                    continue

                item = call.data[0] if isinstance(call.data, list) else call.data
                if not isinstance(item, dict):
                    continue

                fixture = parse_api_fixture_item(item, source=str(call.source or "api-football"))
                if fixture is None:
                    outcome.details.append({"fixture_id": fixture_id, "status": "parse_failed"})
                    continue

                if dry_run:
                    outcome.details.append(
                        {
                            "fixture_id": fixture_id,
                            "status": "dry_run",
                            "fixture_status": fixture.status,
                        }
                    )
                    continue

                if repo.upsert_fixture(fixture, competition_key=competition_key):
                    outcome.fixtures_updated += 1

                if classify_status(fixture.status) == "finished":
                    if repo.upsert_fixture_result(fixture, competition_key=competition_key):
                        outcome.results_updated += 1
                    _sync_outcome_for_fixture(
                        repo=repo,
                        api=api,
                        fixture_id=fixture_id,
                        item=item,
                        fixture=fixture,
                        competition_key=competition_key,
                        outcome=outcome,
                    )
                    finished_for_jsonl.append(fixture)
                    outcome.details.append(
                        {
                            "fixture_id": fixture_id,
                            "status": "finished",
                            "final_score": f"{fixture.home_goals}-{fixture.away_goals}",
                        }
                    )
                else:
                    outcome.details.append(
                        {"fixture_id": fixture_id, "status": "updated", "fixture_status": fixture.status}
                    )
            except Exception as exc:
                logger.exception("Result refresh failed fixture_id=%s", fixture_id)
                outcome.errors += 1
                outcome.details.append({"fixture_id": fixture_id, "status": "error", "reason": str(exc)})

        if finished_for_jsonl and not dry_run:
            outcome.jsonl_saved = save_finished_fixtures(finished_for_jsonl, MatchResultsStore())

        # HOTFIX WC-RESULT-SYNC-2 — ECSE snapshot fixtures (not only WDE stored predictions)
        if not dry_run:
            try:
                from worldcup_predictor.research.ecse_live.result_sync import refresh_ecse_snapshot_results

                ecse_refresh = refresh_ecse_snapshot_results(
                    settings=settings,
                    competition_key=competition_key,
                    limit=limit,
                    dry_run=False,
                )
                outcome.details.append(
                    {
                        "status": "ecse_snapshot_result_sync",
                        "synced": ecse_refresh.synced,
                        "scanned": ecse_refresh.scanned,
                        "ecse_evaluated": ecse_refresh.ecse_evaluated,
                        "errors": ecse_refresh.errors,
                    }
                )
            except Exception:
                logger.exception("ECSE snapshot result sync failed during worldcup_result_refresh")
    finally:
        repo.close()

    logger.info(
        "worldcup_result_refresh %s",
        {k: v for k, v in outcome.__dict__.items() if k != "details"},
    )
    return outcome


def backfill_stored_prediction_outcomes(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    limit: int | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> ResultRefreshOutcome:
    """Backfill HT/events/first-goal for all archived fixtures with finished results."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    api = ApiFootballClient(settings)
    outcome = ResultRefreshOutcome()

    rows = repo.list_worldcup_stored_prediction_rows(competition_key=competition_key)
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    outcome.scanned = len(rows)

    try:
        for row in rows:
            fixture_id = int(row["fixture_id"])
            result_row = repo.get_fixture_result_row(fixture_id)
            fixture_row = repo.get_fixture_row(fixture_id) or {}
            status = str(fixture_row.get("status") or "NS")
            is_finished = classify_status(status) == "finished" or result_row is not None
            if not is_finished:
                continue

            event_count = repo.count_fixture_goal_events(fixture_id)
            if not force and not needs_outcome_backfill(result_row, goal_event_count=event_count):
                outcome.outcomes_skipped_complete += 1
                continue

            if not api.is_configured:
                outcome.skipped_no_api += 1
                continue

            try:
                call = api.get_fixture_by_id(fixture_id)
                outcome.api_fetches += 1
                if not call.data:
                    continue
                item = call.data[0] if isinstance(call.data, list) else call.data
                if not isinstance(item, dict):
                    continue
                fixture = parse_api_fixture_item(item, source=str(call.source or "api-football"))
                if fixture is None:
                    continue
                if dry_run:
                    outcome.details.append({"fixture_id": fixture_id, "status": "dry_run_backfill"})
                    continue

                repo.upsert_fixture(fixture, competition_key=competition_key)
                if classify_status(fixture.status) == "finished":
                    if repo.upsert_fixture_result(fixture, competition_key=competition_key):
                        outcome.results_updated += 1
                    _sync_outcome_for_fixture(
                        repo=repo,
                        api=api,
                        fixture_id=fixture_id,
                        item=item,
                        fixture=fixture,
                        competition_key=competition_key,
                        outcome=outcome,
                    )
            except Exception:
                logger.exception("Outcome backfill failed fixture_id=%s", fixture_id)
                outcome.errors += 1
    finally:
        repo.close()

    return outcome
