"""National team injury impact engine (Phase 32B/32E)."""



from __future__ import annotations



from typing import Any



from worldcup_predictor.domain.intelligence import MatchIntelligenceReport

from worldcup_predictor.intelligence.national_team._shared import clamp, safe_list





IMPACT_WEIGHTS = {

    "critical": 18.0,

    "important": 10.0,

    "rotation": 5.0,

    "depth": 2.0,

}



NEUTRAL_UNKNOWN = 55.0

NEUTRAL_CONFIRMED_HEALTHY = 65.0

LISTED_NO_ABSENCES = 58.0





def _categorize(player: dict[str, Any]) -> str:

    reason = str(player.get("reason") or player.get("type") or "").lower()

    pdata = player.get("player") if isinstance(player.get("player"), dict) else player

    pos = str(pdata.get("pos") or pdata.get("position") or "").upper()

    if any(k in reason for k in ("suspended", "red card", "ban")):

        return "critical"

    if pos in {"G", "GK"}:

        return "critical"

    if pos in {"F", "FW", "ST", "CF"}:

        return "important"

    if pos in {"M", "MF", "CM", "AM", "DM"}:

        return "important"

    if pos in {"D", "DF", "CB", "LB", "RB"}:

        return "rotation"

    if "injury" in reason or "doubtful" in reason:

        return "important"

    return "depth"





def _side_data(team_intel) -> tuple[list[Any], bool, bool]:

    inj = team_intel.injuries

    if inj is None:

        return [], False, False

    players = safe_list(inj.players)

    available_flag = bool(inj.available)

    has_rows = len(players) > 0

    return players, available_flag, has_rows





def injury_impact_score(report: MatchIntelligenceReport) -> tuple[float, dict[str, Any]]:

    if "injuries" in (report.missing_data or []):

        return NEUTRAL_UNKNOWN, {

            "explanation": ["Injury data missing — neutral injury impact."],

            "injury_data_state": "missing",

        }



    def side_impact(players: list[Any]) -> dict[str, Any]:

        buckets = {"critical": 0, "important": 0, "rotation": 0, "depth": 0}

        listed: list[dict[str, Any]] = []

        for row in players:

            if not isinstance(row, dict):

                continue

            cat = _categorize(row)

            buckets[cat] += 1

            pdata = row.get("player") if isinstance(row.get("player"), dict) else row

            listed.append(

                {

                    "name": pdata.get("name"),

                    "category": cat,

                    "reason": row.get("reason") or pdata.get("reason"),

                }

            )

        penalty = sum(buckets[k] * IMPACT_WEIGHTS[k] for k in buckets)

        return {"buckets": buckets, "penalty": round(penalty, 1), "players": listed[:12]}



    home_players, home_avail, home_has = _side_data(report.home_team)

    away_players, away_avail, away_has = _side_data(report.away_team)

    home = side_impact(home_players)

    away = side_impact(away_players)

    total_penalty = float(home["penalty"]) + float(away["penalty"])



    if total_penalty > 0:

        score = clamp(100 - total_penalty * 0.55, 25, 72)

        state = "unavailable_players_listed"

    elif home_has or away_has:

        score = LISTED_NO_ABSENCES

        state = "listed_zero_penalty"

    elif home_avail and away_avail:

        score = NEUTRAL_CONFIRMED_HEALTHY

        state = "confirmed_healthy"

    elif home_avail or away_avail:

        score = 58.0

        state = "partial_availability"

    else:

        score = NEUTRAL_UNKNOWN

        state = "unknown_empty_lists"



    detail = {

        "home": home,

        "away": away,

        "total_penalty": round(total_penalty, 1),

        "injury_data_state": state,

        "explanation": [

            f"Injury impact ({state}): penalty {round(total_penalty, 1)} → score {round(score, 1)}.",

        ],

    }

    return round(score, 1), detail

