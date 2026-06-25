"""Player intelligence layer — Phase 46D."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.provider_utilization.models import (
    PlayerIntelligenceProfile,
    PlayerIntelligenceResult,
)


def _count_goals_from_events(events: list[dict[str, Any]], player: str) -> int:
    name = player.lower()
    count = 0
    for raw in events:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("type") or "").lower() != "goal":
            continue
        player_block = raw.get("player") or {}
        pname = player_block.get("name") if isinstance(player_block, dict) else raw.get("player_name")
        if pname and name in str(pname).lower():
            count += 1
    return count


def _lineup_players(lineups: dict[str, Any] | None, side: str) -> list[str]:
    if not isinstance(lineups, dict):
        return []
    block = lineups.get(side) or lineups.get(f"{side}_team") or {}
    if not isinstance(block, dict):
        return []
    start_xi = block.get("startXI") or block.get("start_xi") or block.get("players") or []
    names: list[str] = []
    for row in start_xi:
        if not isinstance(row, dict):
            continue
        player = row.get("player") if isinstance(row.get("player"), dict) else row
        if isinstance(player, dict) and player.get("name"):
            names.append(str(player["name"]))
    return names


def build_player_intelligence(report: MatchIntelligenceReport) -> PlayerIntelligenceResult:
    """Expand player signals from lineups, events, and injuries."""
    fixture_id = int(report.fixture_id)
    sources: list[str] = []
    profiles: list[PlayerIntelligenceProfile] = []

    events = report.fixture_events or []
    lineups = report.lineups or {}
    if events:
        sources.append("api-football_events")
    if lineups:
        sources.append("api-football_lineups")

    home_injuries = (report.home_team.injuries.players if report.home_team.injuries else []) or []
    away_injuries = (report.away_team.injuries.players if report.away_team.injuries else []) or []
    unavailable = {
        str(p.get("name") or p.get("player", {}).get("name") or "").lower()
        for p in home_injuries + away_injuries
        if isinstance(p, dict)
    }
    unavailable.discard("")

    for side, team_intel in (("home", report.home_team), ("away", report.away_team)):
        team_name = team_intel.team_name
        for player in _lineup_players(lineups, side):
            goals = _count_goals_from_events(events, player)
            available = player.lower() not in unavailable
            lineup_conf = 0.85 if available else 0.35
            profiles.append(
                PlayerIntelligenceProfile(
                    player=player,
                    team=team_name,
                    recent_goals=goals,
                    recent_assists=0,
                    form_score=round(min(100.0, 50 + goals * 15), 1),
                    minutes_played=90 if available else None,
                    available=available,
                    lineup_confidence=lineup_conf,
                )
            )

    profiles.sort(key=lambda p: (p.recent_goals, p.lineup_confidence or 0), reverse=True)
    top = profiles[0] if profiles else None
    first_goal_team = None
    if events:
        first = events[0]
        if isinstance(first, dict):
            team_block = first.get("team") or {}
            first_goal_team = team_block.get("name") if isinstance(team_block, dict) else None

    goalscorer_conf = None
    if top:
        goalscorer_conf = round(min(0.75, 0.35 + top.recent_goals * 0.08 + (top.lineup_confidence or 0) * 0.2), 3)

    return PlayerIntelligenceResult(
        fixture_id=fixture_id,
        profiles=profiles[:22],
        top_scorer_candidate=top.player if top else None,
        first_goal_candidate=top.player if top else None,
        first_goal_team_hint=first_goal_team,
        goalscorer_confidence=goalscorer_conf,
        sources_used=sources,
    )
