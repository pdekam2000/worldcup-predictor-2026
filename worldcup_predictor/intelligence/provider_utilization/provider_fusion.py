"""Provider fusion policy implementation — Phase 46D."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.intelligence.provider_utilization.models import UnifiedMatchEvent

FUSION_POLICY_VERSION = "46d_api_football_primary_v1"


def _event_key(event: UnifiedMatchEvent) -> tuple[Any, ...]:
    return (
        event.event_type,
        event.minute,
        event.extra_minute,
        (event.team or "").lower(),
        (event.player or "").lower(),
    )


def merge_event_layers(
    primary: list[UnifiedMatchEvent],
    secondary: list[UnifiedMatchEvent],
) -> tuple[list[UnifiedMatchEvent], list[str]]:
    """
    Merge event lists — API-Football primary, Sportmonks fills gaps.

    Conflict: same minute/type/team/player from both → keep primary.
    """
    notes: list[str] = []
    merged: dict[tuple[Any, ...], UnifiedMatchEvent] = {}
    for event in primary:
        merged[_event_key(event)] = event
    added = 0
    for event in secondary:
        key = _event_key(event)
        if key not in merged:
            merged[key] = UnifiedMatchEvent(
                sort_index=event.sort_index,
                event_type=event.event_type,
                minute=event.minute,
                extra_minute=event.extra_minute,
                team=event.team,
                team_id=event.team_id,
                player=event.player,
                assist=event.assist,
                detail=event.detail,
                source="merged",
                is_penalty=event.is_penalty,
                is_own_goal=event.is_own_goal,
                card_type=event.card_type,
                sub_in=event.sub_in,
                sub_out=event.sub_out,
            )
            added += 1
    if added:
        notes.append(f"sportmonks_gap_fill_events={added}")
    if primary and secondary:
        notes.append("conflict_rule=primary_wins")
    ordered = sorted(merged.values(), key=lambda e: (e.minute if e.minute is not None else 9999, e.extra_minute or 0))
    for idx, event in enumerate(ordered):
        if event.sort_index != idx:
            ordered[idx] = UnifiedMatchEvent(
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
    return ordered, notes


def pick_primary_score(
    *,
    api_score: str | None,
    sportmonks_score: str | None,
    cache_score: str | None = None,
) -> tuple[str | None, str]:
    if api_score:
        return api_score, "api-football"
    if sportmonks_score:
        return sportmonks_score, "sportmonks"
    if cache_score:
        return cache_score, "cache"
    return None, "none"


def pick_entity(
    *,
    entity: str,
    api_value: Any,
    sportmonks_value: Any,
    cache_value: Any = None,
) -> tuple[Any, str]:
    """Generic entity fusion: API-Football > Sportmonks > Cache."""
    if api_value is not None and api_value != "" and api_value != []:
        return api_value, "api-football"
    if sportmonks_value is not None and sportmonks_value != "" and sportmonks_value != []:
        return sportmonks_value, "sportmonks"
    if cache_value is not None and cache_value != "" and cache_value != []:
        return cache_value, "cache"
    return None, "none"
