"""First goalscorer candidate ranking from real available data only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import FirstGoalScorerCandidate
from worldcup_predictor.domain.specialist import MatchSpecialistReport
from worldcup_predictor.prediction.player_position_utils import apply_position_score, is_goalkeeper, normalize_position


def build_first_goal_scorer_candidates(
    report: MatchIntelligenceReport,
    first_goal_team: str,
    *,
    specialist_report: MatchSpecialistReport | None = None,
    limit: int = 3,
) -> tuple[list[FirstGoalScorerCandidate], bool, str | None]:
    """
    Return top scorer candidates, player_data_available flag, and unavailable message.
    Never invents player names. Goalkeepers excluded unless season goal data proves rare penalty role.
    """
    from worldcup_predictor.integrations.api_sports_deep_data import deep_player_rows_for_team

    ranked: dict[str, FirstGoalScorerCandidate] = {}
    had_attacking_data = False

    def add_candidate(
        player: str,
        team: str,
        score: float,
        reason: str,
        data_source: str,
        position: str = "",
        *,
        penalty_gk_goals: float | None = None,
    ) -> None:
        nonlocal had_attacking_data
        name = player.strip()
        if not name or name.startswith("TBD"):
            return
        weighted = apply_position_score(score, position, penalty_gk_goals=penalty_gk_goals)
        if weighted is None:
            return
        if weighted >= 40:
            had_attacking_data = True
        key = f"{name}|{team}"
        pos_label = normalize_position(position)
        existing = ranked.get(key)
        if existing is None or weighted > existing.score:
            ranked[key] = FirstGoalScorerCandidate(
                player=name,
                team=team,
                score=weighted,
                reason=reason if pos_label else f"{reason} (position unknown — lower confidence)",
                data_source=data_source,
                position=pos_label,
            )

    supplemental = getattr(report, "supplemental_sources", None) or {}
    for row in deep_player_rows_for_team(report, first_goal_team):
        if not isinstance(row, dict):
            continue
        score = float(row.get("score_hint") or 55)
        reason_parts = []
        if row.get("data_source") == "api_sports_topscorers":
            reason_parts.append("Tournament top scorer profile")
        else:
            reason_parts.append("Fixture player match statistics")
        if row.get("player_rating") is not None:
            reason_parts.append(f"rating {row.get('player_rating')}")
        if int(row.get("assists") or 0) > 0:
            reason_parts.append(f"{row.get('assists')} assists")
        if int(row.get("key_passes") or 0) > 0:
            reason_parts.append(f"{row.get('key_passes')} key passes")
        reason = " — ".join(reason_parts)
        add_candidate(
            str(row.get("player") or ""),
            str(row.get("team") or first_goal_team),
            score,
            reason,
            str(row.get("data_source") or "api_sports_deep"),
            position=str(row.get("position") or ""),
        )

    player_stats = supplemental.get("rapid_football_stats", {}).get("player_statistics") or []
    if isinstance(player_stats, list):
        for row in player_stats:
            if not isinstance(row, dict):
                continue
            team = str(row.get("team") or row.get("team_name") or "")
            if team and team.lower() != first_goal_team.lower():
                continue
            name = str(row.get("player") or row.get("name") or "")
            position = str(row.get("position") or "")
            goals = _float(row.get("goals") or row.get("season_goals"))
            base = 50.0 + (goals or 0) * 8
            add_candidate(
                name,
                team or first_goal_team,
                base,
                "Season goal tally from supplemental stats",
                "rapid_football_stats",
                position=position,
                penalty_gk_goals=goals if is_goalkeeper(position) else None,
            )

    squad = supplemental.get("rapid_football_stats", {}).get("team_squad") or {}
    for side, players in squad.items() if isinstance(squad, dict) else []:
        if not isinstance(players, list):
            continue
        for row in players:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            position = str(row.get("position") or "")
            team = first_goal_team if side == "home" else report.away_team.team_name
            if side == "away" and first_goal_team.lower() != report.away_team.team_name.lower():
                team = first_goal_team
            add_candidate(name, team, 48.0, "Squad attacker profile", "rapid_football_stats", position=position)

    for lineup in (report.lineups or {}).get("items") or []:
        team = lineup.get("team", {}).get("name", "")
        if team.lower() != first_goal_team.lower():
            continue
        for idx, entry in enumerate(lineup.get("startXI") or []):
            player = entry.get("player", {})
            name = player.get("name")
            if not name:
                continue
            pos = str(player.get("pos") or player.get("position") or "")
            base = max(72.0 - idx * 3, 38.0)
            add_candidate(
                name,
                team,
                base,
                "Listed starter in predicted/official lineup",
                "api_sports_lineups",
                position=pos,
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
                            position=str(row.get("position") or ""),
                        )

    candidates = [
        c for c in sorted(ranked.values(), key=lambda c: c.score, reverse=True)
        if not is_goalkeeper(c.position)
    ][:limit]

    if candidates:
        return candidates, True, None
    if had_attacking_data:
        return [], False, "No reliable attacking scorer candidates after position filtering."
    return [], False, "Player-level scorer data unavailable"


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

# Backward-compatible aliases for tests
_is_goalkeeper = is_goalkeeper
_normalize_position = normalize_position
_apply_position_score = apply_position_score
