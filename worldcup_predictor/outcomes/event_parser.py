"""Parse API-Football goal events into normalized GoalEvent rows — Phase 46C-1."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.outcomes.models import GoalEvent


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_countable_goal(event: dict[str, Any]) -> bool:
    etype = str(event.get("type") or "").strip().lower()
    if etype != "goal":
        return False
    detail = str(event.get("detail") or "").lower()
    if "missed penalty" in detail:
        return False
    return True


def _is_penalty(detail: str) -> bool:
    text = detail.lower()
    return "penalty" in text and "missed" not in text


def _is_own_goal(detail: str) -> bool:
    return "own goal" in detail.lower()


def parse_api_football_goal_events(
    events: list[Any],
    *,
    home_team: str | None = None,
    away_team: str | None = None,
) -> list[GoalEvent]:
    """Normalize API-Football fixtures/events payload into ordered goal events."""
    parsed: list[GoalEvent] = []
    sort_index = 0
    for raw in events:
        if not isinstance(raw, dict):
            continue
        if not _is_countable_goal(raw):
            continue
        time_block = raw.get("time") or {}
        minute = _int_or_none(time_block.get("elapsed"))
        extra = _int_or_none(time_block.get("extra"))
        team_block = raw.get("team") or {}
        player_block = raw.get("player") or {}
        assist_block = raw.get("assist") or {}
        detail = str(raw.get("detail") or "").strip() or None
        team_name = team_block.get("name")
        team_id = _int_or_none(team_block.get("id"))
        player = player_block.get("name")
        assist = assist_block.get("name") if isinstance(assist_block, dict) else None
        parsed.append(
            GoalEvent(
                sort_index=sort_index,
                minute=minute,
                extra_minute=extra,
                team=str(team_name) if team_name else None,
                team_id=team_id,
                player=str(player) if player else None,
                assist=str(assist) if assist else None,
                is_penalty=_is_penalty(detail or ""),
                is_own_goal=_is_own_goal(detail or ""),
                detail=detail,
            )
        )
        sort_index += 1

    parsed.sort(key=lambda e: (e.minute if e.minute is not None else 9999, e.extra_minute or 0, e.sort_index))
    for idx, event in enumerate(parsed):
        if event.sort_index != idx:
            parsed[idx] = GoalEvent(
                sort_index=idx,
                minute=event.minute,
                extra_minute=event.extra_minute,
                team=event.team,
                team_id=event.team_id,
                player=event.player,
                assist=event.assist,
                is_penalty=event.is_penalty,
                is_own_goal=event.is_own_goal,
                detail=event.detail,
            )
    return parsed


def first_goal_from_events(events: list[GoalEvent]) -> GoalEvent | None:
    return events[0] if events else None
