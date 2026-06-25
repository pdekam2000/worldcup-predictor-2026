"""Refresh finished PL fixture results for published goal-timing predictions (Phase 51E)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.prediction_history_evaluation import FixtureOutcomeResolver
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.goal_timing.storage.repository import GoalTimingRepository
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.outcomes.outcome_persistence import (
    build_parsed_outcome,
    needs_outcome_backfill,
    persist_fixture_outcome,
    should_fetch_events_for_fixture,
)
from worldcup_predictor.schedule.match_center import classify_status

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _kickoff_passed(match_date: Any, *, now_iso: str) -> bool:
    if match_date is None:
        return False
    try:
        if hasattr(match_date, "isoformat"):
            kickoff = match_date.isoformat()
        else:
            kickoff = str(match_date).replace("Z", "+00:00")
            if "T" in kickoff:
                kickoff = datetime.fromisoformat(kickoff).replace(tzinfo=None).isoformat()
    except ValueError:
        return False
    return kickoff <= now_iso


@dataclass
class GoalTimingResultRefreshOutcome:
    scanned: int = 0
    api_fetches: int = 0
    api_event_fetches: int = 0
    fixtures_updated: int = 0
    results_updated: int = 0
    outcomes_persisted: int = 0
    skipped_not_due: int = 0
    skipped_already_complete: int = 0
    skipped_no_api: int = 0
    errors: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)


def refresh_goal_timing_fixture_results(
    *,
    settings: Settings | None = None,
    limit: int | None = 50,
    max_api_calls: int = 50,
    dry_run: bool = False,
) -> GoalTimingResultRefreshOutcome:
    """Detect finished matches and refresh SQLite results for goal-timing prediction fixtures."""
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    gt_repo = GoalTimingRepository(settings)
    resolver = FixtureOutcomeResolver(settings)
    api = ApiFootballClient(settings)
    outcome = GoalTimingResultRefreshOutcome()
    now_iso = _utc_now_iso()

    predictions = gt_repo.list_published_predictions(limit=500)
    due: list[dict[str, Any]] = []
    for pred in predictions:
        if _kickoff_passed(pred.get("match_date"), now_iso=now_iso):
            due.append(pred)
        else:
            outcome.skipped_not_due += 1

    if limit is not None:
        due = due[: max(0, int(limit))]
    outcome.scanned = len(due)

    api_calls = 0
    try:
        for pred in due:
            if api_calls >= max_api_calls:
                outcome.details.append({"status": "api_cap_reached"})
                break

            fixture_id = int(pred["fixture_id"])
            comp_key = str(pred.get("competition_key") or "premier_league")
            existing = resolver.resolve(fixture_id)
            result_row = repo.get_fixture_result_row(fixture_id)
            event_count = repo.count_fixture_goal_events(fixture_id)
            if (
                existing.is_finished
                and existing.final_score
                and result_row
                and not needs_outcome_backfill(result_row, goal_event_count=event_count)
            ):
                outcome.skipped_already_complete += 1
                continue

            if not api.is_configured:
                outcome.skipped_no_api += 1
                continue

            try:
                call = api.get_fixture_by_id(fixture_id)
                api_calls += 1
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
                    outcome.details.append(
                        {"fixture_id": fixture_id, "status": "dry_run", "fixture_status": fixture.status}
                    )
                    continue

                if repo.upsert_fixture(
                    fixture,
                    competition_key=comp_key,
                    league_id=pred.get("league_id"),
                    season=pred.get("season"),
                ):
                    outcome.fixtures_updated += 1

                if classify_status(fixture.status) == "finished":
                    if repo.upsert_fixture_result(fixture, competition_key=comp_key):
                        outcome.results_updated += 1

                    if should_fetch_events_for_fixture(fixture):
                        events_raw = item.get("events") if isinstance(item.get("events"), list) else []
                        if not events_raw and api_calls < max_api_calls:
                            ev_call = api.get_fixture_events(fixture_id)
                            api_calls += 1
                            outcome.api_event_fetches += 1
                            if ev_call.ok and isinstance(ev_call.data, list):
                                events_raw = ev_call.data
                        parsed = build_parsed_outcome(
                            fixture,
                            events_raw,
                            outcome_source=str(fixture.source or "api-football"),
                        )
                        if persist_fixture_outcome(repo, parsed, competition_key=comp_key):
                            outcome.outcomes_persisted += 1
            except Exception as exc:
                logger.exception("Goal timing result refresh failed fixture_id=%s", fixture_id)
                outcome.errors += 1
                outcome.details.append({"fixture_id": fixture_id, "status": "error", "reason": str(exc)})
    finally:
        repo.close()

    logger.info(
        "goal_timing_result_refresh scanned=%d api_fetches=%d fixtures_updated=%d results_updated=%d "
        "outcomes_persisted=%d skipped_not_due=%d skipped_already_complete=%d skipped_no_api=%d errors=%d",
        outcome.scanned,
        outcome.api_fetches,
        outcome.fixtures_updated,
        outcome.results_updated,
        outcome.outcomes_persisted,
        outcome.skipped_not_due,
        outcome.skipped_already_complete,
        outcome.skipped_no_api,
        outcome.errors,
    )
    return outcome
