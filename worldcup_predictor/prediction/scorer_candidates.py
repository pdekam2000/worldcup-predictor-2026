"""First goalscorer candidate ranking from real available data only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import FirstGoalScorerCandidate
from worldcup_predictor.domain.specialist import MatchSpecialistReport

ATTACK_POSITIONS = frozenset({"F", "FW", "ST", "CF", "LW", "RW", "AM", "M"})


def build_first_goal_scorer_candidates(
    report: MatchIntelligenceReport,
    first_goal_team: str,
    *,
    specialist_report: MatchSpecialistReport | None = None,
    limit: int = 3,
) -> tuple[list[FirstGoalScorerCandidate], bool, str | None]:
    """
    Return top scorer candidates, player_data_available flag, and unavailable message.
    Never invents player names.
    """
    ranked: dict[str, FirstGoalScorerCandidate] = {}

    def add_candidate(
        player: str,
        team: str,
        score: float,
        reason: str,
        data_source: str,
    ) -> None:
        name = player.strip()
        if not name or name.startswith("TBD"):
            return
        key = f"{name}|{team}"
        existing = ranked.get(key)
        if existing is None or score > existing.score:
            ranked[key] = FirstGoalScorerCandidate(
                player=name,
                team=team,
                score=round(score, 2),
                reason=reason,
                data_source=data_source,
            )

    supplemental = getattr(report, "supplemental_sources", None) or {}
    player_stats = supplemental.get("rapid_football_stats", {}).get("player_statistics") or []
    if isinstance(player_stats, list):
        for row in player_stats:
            if not isinstance(row, dict):
                continue
            team = str(row.get("team") or row.get("team_name") or "")
            if team and team.lower() != first_goal_team.lower():
                continue
            name = str(row.get("player") or row.get("name") or "")
            goals = _float(row.get("goals") or row.get("season_goals"))
            score = 50.0 + (goals or 0) * 8
            add_candidate(name, team or first_goal_team, score, "Season goal tally from supplemental stats", "rapid_football_stats")

    squad = supplemental.get("rapid_football_stats", {}).get("team_squad") or {}
    for side, players in squad.items() if isinstance(squad, dict) else []:
        if not isinstance(players, list):
            continue
        for row in players:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            position = str(row.get("position") or "").upper()
            team = first_goal_team if side == "home" else report.away_team.team_name
            if side == "away" and first_goal_team.lower() != report.away_team.team_name.lower():
                team = first_goal_team
            if position and position not in ATTACK_POSITIONS:
                continue
            add_candidate(name, team, 45.0, "Squad attacker profile", "rapid_football_stats")

    for lineup in (report.lineups or {}).get("items") or []:
        team = lineup.get("team", {}).get("name", "")
        if team.lower() != first_goal_team.lower():
            continue
        for idx, entry in enumerate(lineup.get("startXI") or []):
            player = entry.get("player", {})
            name = player.get("name")
            if not name:
                continue
            pos = str(player.get("pos") or player.get("position") or "").upper()
            base = 60.0 - idx * 4
            if pos in ATTACK_POSITIONS or not pos:
                base += 5
            add_candidate(
                name,
                team,
                base,
                "Listed starter in predicted/official lineup",
                "api_sports_lineups",
            )

    if specialist_report:
        pq = specialist_report.signal("player_quality_agent")
        if pq and pq.is_usable:
            structured = pq.signals.get("first_goal_scorer_candidates") or []
            if isinstance(structured, list):
                for row in structured:
                    if isinstance(row, dict):
                        add_candidate(
                            str(row.get("player", "")),
                            str(row.get("team", first_goal_team)),
                            float(row.get("score", 55)),
                            str(row.get("reason", "Player quality signal")),
                            str(row.get("data_source", "player_quality_agent")),
                        )

    candidates = sorted(ranked.values(), key=lambda c: c.score, reverse=True)[:limit]
    if candidates:
        return candidates, True, None
    return [], False, "Player-level scorer data unavailable"




def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
