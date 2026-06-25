"""Unified match event layer — API-Football + Sportmonks merge (Phase 46D)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.intelligence.provider_utilization.models import (
    UnifiedEventLayerResult,
    UnifiedMatchEvent,
)
from worldcup_predictor.intelligence.provider_utilization.provider_fusion import (
    FUSION_POLICY_VERSION,
    merge_event_layers,
)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _event_type_from_api_football(raw: dict[str, Any]) -> str:
    etype = str(raw.get("type") or "").strip().lower()
    detail = str(raw.get("detail") or "").lower()
    if etype == "goal":
        if "own goal" in detail:
            return "own_goal"
        if "penalty" in detail and "missed" not in detail:
            return "penalty_goal"
        return "goal"
    if etype == "card":
        return "card"
    if etype == "subst":
        return "substitution"
    return "other"


def parse_api_football_events(events: list[Any] | None) -> list[UnifiedMatchEvent]:
    parsed: list[UnifiedMatchEvent] = []
    if not events:
        return parsed
    sort_index = 0
    for raw in events:
        if not isinstance(raw, dict):
            continue
        etype = _event_type_from_api_football(raw)
        time_block = raw.get("time") or {}
        minute = _int_or_none(time_block.get("elapsed"))
        extra = _int_or_none(time_block.get("extra"))
        team_block = raw.get("team") or {}
        player_block = raw.get("player") or {}
        assist_block = raw.get("assist") or {}
        detail = str(raw.get("detail") or "").strip() or None
        card_type = None
        if etype == "card":
            if "red" in (detail or "").lower():
                card_type = "red"
            else:
                card_type = "yellow"
        sub_in = None
        sub_out = None
        if etype == "substitution":
            sub_in = player_block.get("name")
            assist_block = raw.get("assist") or {}
            if isinstance(assist_block, dict):
                sub_out = assist_block.get("name")
        parsed.append(
            UnifiedMatchEvent(
                sort_index=sort_index,
                event_type=etype,  # type: ignore[arg-type]
                minute=minute,
                extra_minute=extra,
                team=str(team_block.get("name")) if team_block.get("name") else None,
                team_id=_int_or_none(team_block.get("id")),
                player=str(player_block.get("name")) if player_block.get("name") else None,
                assist=str(assist_block.get("name")) if isinstance(assist_block, dict) and assist_block.get("name") else None,
                detail=detail,
                source="api-football",
                is_penalty="penalty" in (detail or "").lower() and "missed" not in (detail or "").lower(),
                is_own_goal=etype == "own_goal",
                card_type=card_type,
                sub_in=sub_in,
                sub_out=sub_out,
            )
        )
        sort_index += 1
    parsed.sort(key=lambda e: (e.minute if e.minute is not None else 9999, e.extra_minute or 0, e.sort_index))
    for idx, event in enumerate(parsed):
        if event.sort_index != idx:
            parsed[idx] = UnifiedMatchEvent(
                sort_index=idx,
                event_type=event.event_type,
                minute=event.minute,
                extra_minute=event.extra_minute,
                team=event.team,
                team_id=event.team_id,
                player=event.player,
                assist=event.assist,
                detail=event.detail,
                source=event.source,
                is_penalty=event.is_penalty,
                is_own_goal=event.is_own_goal,
                card_type=event.card_type,
                sub_in=event.sub_in,
                sub_out=event.sub_out,
            )
    return parsed


def _sportmonks_type_name(raw: dict[str, Any]) -> str:
    type_block = raw.get("type") or {}
    if isinstance(type_block, dict):
        return str(type_block.get("name") or type_block.get("developer_name") or "").lower()
    return str(raw.get("type_id") or "").lower()


def parse_sportmonks_events(
    events: list[Any] | None,
    *,
    participants: list[dict[str, Any]] | None = None,
) -> list[UnifiedMatchEvent]:
    parsed: list[UnifiedMatchEvent] = []
    if not events:
        return parsed
    participant_names: dict[int, str] = {}
    for p in participants or []:
        if not isinstance(p, dict):
            continue
        pid = _int_or_none(p.get("id"))
        name = p.get("name") or (p.get("meta") or {}).get("name")
        if pid and name:
            participant_names[pid] = str(name)

    sort_index = 0
    for raw in events:
        if not isinstance(raw, dict):
            continue
        type_name = _sportmonks_type_name(raw)
        minute = _int_or_none(raw.get("minute"))
        extra = _int_or_none(raw.get("extra_minute"))
        participant_id = _int_or_none(raw.get("participant_id"))
        team = participant_names.get(participant_id) if participant_id else None
        player = raw.get("player_name") or (raw.get("player") or {}).get("name") if isinstance(raw.get("player"), dict) else None
        detail = type_name or None

        etype: str = "other"
        card_type = None
        is_penalty = False
        is_own_goal = False
        if "goal" in type_name:
            etype = "goal"
            if "own" in type_name:
                etype = "own_goal"
                is_own_goal = True
            elif "penalty" in type_name:
                etype = "penalty_goal"
                is_penalty = True
        elif "yellow" in type_name or "red" in type_name or "card" in type_name:
            etype = "card"
            card_type = "red" if "red" in type_name else "yellow"
        elif "substitut" in type_name:
            etype = "substitution"

        parsed.append(
            UnifiedMatchEvent(
                sort_index=sort_index,
                event_type=etype,  # type: ignore[arg-type]
                minute=minute,
                extra_minute=extra,
                team=team,
                team_id=participant_id,
                player=str(player) if player else None,
                assist=None,
                detail=detail,
                source="sportmonks",
                is_penalty=is_penalty,
                is_own_goal=is_own_goal,
                card_type=card_type,
            )
        )
        sort_index += 1

    parsed.sort(key=lambda e: (e.minute if e.minute is not None else 9999, e.extra_minute or 0, e.sort_index))
    return parsed


def build_unified_event_layer(
    *,
    fixture_id: int,
    api_football_events: list[Any] | None = None,
    sportmonks_raw: dict[str, Any] | None = None,
    cached_events: list[dict[str, Any]] | None = None,
) -> UnifiedEventLayerResult:
    """Cache-first merge of API-Football and Sportmonks events."""
    sources: list[str] = []
    api_events: list[UnifiedMatchEvent] = []
    sm_events: list[UnifiedMatchEvent] = []

    if cached_events:
        api_events = [
            UnifiedMatchEvent(
                sort_index=int(row.get("sort_index", i)),
                event_type=row.get("event_type", "other"),  # type: ignore[arg-type]
                minute=row.get("minute"),
                extra_minute=row.get("extra_minute"),
                team=row.get("team"),
                team_id=row.get("team_id"),
                player=row.get("player"),
                assist=row.get("assist"),
                detail=row.get("detail"),
                source=row.get("source", "cache"),  # type: ignore[arg-type]
                is_penalty=bool(row.get("is_penalty")),
                is_own_goal=bool(row.get("is_own_goal")),
                card_type=row.get("card_type"),
                sub_in=row.get("sub_in"),
                sub_out=row.get("sub_out"),
            )
            for i, row in enumerate(cached_events)
            if isinstance(row, dict)
        ]
        sources.append("cache")
    elif api_football_events:
        api_events = parse_api_football_events(api_football_events)
        if api_events:
            sources.append("api-football")

    if sportmonks_raw:
        sm_list = sportmonks_raw.get("events") if isinstance(sportmonks_raw.get("events"), list) else []
        participants = sportmonks_raw.get("participants") if isinstance(sportmonks_raw.get("participants"), list) else []
        sm_events = parse_sportmonks_events(sm_list, participants=participants)
        if sm_events:
            sources.append("sportmonks")

    merged, notes = merge_event_layers(api_events, sm_events)
    goal_count = sum(1 for e in merged if e.event_type in {"goal", "penalty_goal", "own_goal"})
    card_count = sum(1 for e in merged if e.event_type == "card")
    sub_count = sum(1 for e in merged if e.event_type == "substitution")

    return UnifiedEventLayerResult(
        fixture_id=fixture_id,
        events=merged,
        sources_used=sources,
        merge_policy=FUSION_POLICY_VERSION,
        goal_count=goal_count,
        card_count=card_count,
        substitution_count=sub_count,
    )


def goal_events_for_outcome_persistence(events: list[UnifiedMatchEvent]) -> list[dict[str, Any]]:
    """Bridge to Phase 46C goal event persistence format."""
    out: list[dict[str, Any]] = []
    for event in events:
        if event.event_type not in {"goal", "penalty_goal", "own_goal"}:
            continue
        out.append(
            {
                "type": "Goal",
                "detail": event.detail or ("Own Goal" if event.is_own_goal else "Normal Goal"),
                "time": {"elapsed": event.minute, "extra": event.extra_minute},
                "team": {"id": event.team_id, "name": event.team},
                "player": {"name": event.player},
                "assist": {"name": event.assist} if event.assist else None,
            }
        )
    return out
