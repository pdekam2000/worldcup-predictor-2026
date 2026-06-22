"""Persist parsed fixture outcomes — Phase 46C-1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.outcomes.event_parser import first_goal_from_events, parse_api_football_goal_events
from worldcup_predictor.outcomes.models import GoalEvent, ParsedFixtureOutcome
from worldcup_predictor.schedule.match_center import classify_status

_CANCELLED_STATUSES = frozenset({"CANC", "CANCELLED", "AWD", "WO", "AWARDED"})
_ABANDONED_STATUSES = frozenset({"ABD", "ABANDONED"})
_POSTPONED_STATUSES = frozenset({"PST", "POSTPONED", "SUSP", "INT"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def normalize_match_outcome_type(status: str | None) -> str:
    code = str(status or "UNKNOWN").upper()
    if code == "FT":
        return "FT"
    if code == "AET":
        return "AET"
    if code == "PEN":
        return "PEN"
    if code in _CANCELLED_STATUSES:
        return "CANCELLED"
    if code in _ABANDONED_STATUSES:
        return "ABANDONED"
    if code in _POSTPONED_STATUSES:
        return "POSTPONED"
    if code in {"FT_PEN", "FTP"}:
        return "PEN"
    return code or "UNKNOWN"


def ht_result_from_goals(ht_home: int | None, ht_away: int | None) -> str | None:
    if ht_home is None or ht_away is None:
        return None
    if ht_home > ht_away:
        return "home_win"
    if ht_home < ht_away:
        return "away_win"
    return "draw"


def build_parsed_outcome(
    fixture: TournamentFixture,
    events_raw: list[Any] | None,
    *,
    outcome_source: str = "api-football",
) -> ParsedFixtureOutcome:
    goal_events = parse_api_football_goal_events(
        events_raw or [],
        home_team=fixture.home_team,
        away_team=fixture.away_team,
    )
    ht_home = fixture.halftime_home_goals
    ht_away = fixture.halftime_away_goals
    ht_score = f"{ht_home}-{ht_away}" if ht_home is not None and ht_away is not None else None
    ht_result = ht_result_from_goals(ht_home, ht_away)

    first = first_goal_from_events(goal_events)
    first_team = first.team if first else None
    first_player = first.player if first else None
    first_minute = first.minute if first else None
    first_extra = first.extra_minute if first else None

    return ParsedFixtureOutcome(
        fixture_id=int(fixture.fixture_id),
        match_outcome_type=normalize_match_outcome_type(fixture.status),
        ht_home_goals=ht_home,
        ht_away_goals=ht_away,
        ht_result=ht_result,
        ht_score=ht_score,
        first_goal_team=first_team,
        first_goal_player=first_player,
        first_goal_minute=first_minute,
        first_goal_extra_minute=first_extra,
        goal_events=goal_events,
        outcome_source=outcome_source,
    )


def needs_outcome_backfill(result_row: dict[str, Any] | None, *, goal_event_count: int = 0) -> bool:
    """True when HT/first-goal/events detail should be fetched or refreshed."""
    if not result_row:
        return False
    if not result_row.get("outcome_persisted_at"):
        return True
    total_goals = int(result_row.get("total_goals") or 0)
    if total_goals > 0 and goal_event_count == 0:
        return True
    if result_row.get("halftime_score") and result_row.get("ht_home_goals") is None:
        return True
    return False


def persist_fixture_outcome(
    repo: Any,
    parsed: ParsedFixtureOutcome,
    *,
    competition_key: str = "world_cup_2026",
) -> bool:
    """Idempotent upsert of outcome detail + goal events."""
    now = _utc_now_iso()
    updated = repo.update_fixture_outcome_detail(
        parsed.fixture_id,
        competition_key=competition_key,
        ht_home_goals=parsed.ht_home_goals,
        ht_away_goals=parsed.ht_away_goals,
        ht_result=parsed.ht_result,
        first_goal_team=parsed.first_goal_team,
        first_goal_player=parsed.first_goal_player,
        first_goal_minute=parsed.first_goal_minute,
        first_goal_extra_minute=parsed.first_goal_extra_minute,
        match_outcome_type=parsed.match_outcome_type,
        outcome_persisted_at=now,
        outcome_source=parsed.outcome_source,
    )
    events_written = repo.replace_fixture_goal_events(parsed.fixture_id, parsed.goal_events)
    return updated or events_written


def should_fetch_events_for_fixture(fixture: TournamentFixture) -> bool:
    if classify_status(fixture.status) != "finished":
        return False
    return True
