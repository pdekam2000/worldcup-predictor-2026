"""National team squad strength engine (Phase 32B)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.intelligence.national_team._shared import clamp, safe_list


def _lineup_strength(lineups: dict[str, Any] | None, team_name: str) -> dict[str, Any]:
    items = safe_list((lineups or {}).get("items"))
    for block in items:
        if not isinstance(block, dict):
            continue
        name = str((block.get("team") or {}).get("name") or "")
        if team_name.lower() not in name.lower() and name.lower() not in team_name.lower():
            continue
        starters = safe_list(block.get("startXI"))
        subs = safe_list(block.get("substitutes"))
        return {
            "starters": len(starters),
            "subs": len(subs),
            "formation": block.get("formation"),
            "available": bool(starters),
        }
    return {"starters": 0, "subs": 0, "formation": None, "available": False}


def _player_bucket(player: dict[str, Any]) -> str:
    reason = str(player.get("reason") or player.get("type") or "").lower()
    pos = str((player.get("player") or player.get("pos") or "")).upper()
    if any(k in reason for k in ("suspended", "red", "ban")):
        return "critical"
    if pos in {"G", "GK"} or "goalkeeper" in reason:
        return "critical"
    if pos in {"F", "FW", "ST"} or "striker" in reason:
        return "important"
    if pos in {"M", "MF", "CM", "DM", "AM"}:
        return "important"
    if pos in {"D", "DF", "CB", "LB", "RB"}:
        return "rotation"
    if any(k in reason for k in ("injury", "doubtful")):
        return "important"
    return "depth"


def squad_strength_score(report: MatchIntelligenceReport) -> tuple[float, dict[str, Any]]:
    home_name = report.home_team.team_name
    away_name = report.away_team.team_name
    lineups = report.lineups or {}
    home_line = _lineup_strength(lineups, home_name)
    away_line = _lineup_strength(lineups, away_name)

    def side_block(team_name: str, injuries_list: list[Any]) -> dict[str, Any]:
        unavailable = [p for p in injuries_list if isinstance(p, dict)]
        buckets = {"critical": 0, "important": 0, "rotation": 0, "depth": 0}
        for row in unavailable:
            buckets[_player_bucket(row)] += 1
        lineup = home_line if team_name == home_name else away_line
        starters = int(lineup.get("starters") or 0)
        starter_av = clamp(starters / 11 * 100 if starters else 55, 20, 100)
        gk_stable = 85.0 if buckets["critical"] == 0 and starters >= 1 else 55.0
        attack = clamp(70 - buckets["important"] * 8 - buckets["critical"] * 15, 25, 90)
        midfield = clamp(68 - buckets["rotation"] * 4 - buckets["important"] * 6, 25, 90)
        defense = clamp(66 - buckets["rotation"] * 5 - buckets["critical"] * 12, 25, 90)
        captain = 80.0 if starters >= 11 else 60.0
        return {
            "starter_availability_pct": round(starter_av, 1),
            "captain_availability": captain,
            "goalkeeper_stability": gk_stable,
            "attack_strength": attack,
            "midfield_strength": midfield,
            "defense_strength": defense,
            "unavailable_buckets": buckets,
            "lineup": lineup,
        }

    home_inj = safe_list(report.home_team.injuries.players if report.home_team.injuries else [])
    away_inj = safe_list(report.away_team.injuries.players if report.away_team.injuries else [])
    home = side_block(home_name, home_inj)
    away = side_block(away_name, away_inj)

    home_avg = (
        home["starter_availability_pct"]
        + home["attack_strength"]
        + home["midfield_strength"]
        + home["defense_strength"]
        + home["goalkeeper_stability"]
    ) / 5
    away_avg = (
        away["starter_availability_pct"]
        + away["attack_strength"]
        + away["midfield_strength"]
        + away["defense_strength"]
        + away["goalkeeper_stability"]
    ) / 5
    score = clamp((home_avg + away_avg) / 2, 25, 95)
    if lineups.get("available"):
        score = clamp(score + 5, 25, 95)

    detail = {
        "home": home,
        "away": away,
        "explanation": [
            f"Squad strength from lineups/injuries: home {round(home_avg,1)}, away {round(away_avg,1)}.",
        ],
    }
    return round(score, 1), detail
