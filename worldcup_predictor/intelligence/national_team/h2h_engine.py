"""National team H2H engine — recency-weighted meetings (Phase 32B)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.intelligence.national_team._shared import (
    clamp,
    goals_from_fixture,
    parse_kickoff,
    recency_weight,
    safe_list,
    team_side_in_fixture,
    years_since,
)


def build_h2h_detail(
    meetings: list[dict[str, Any]] | None,
    *,
    home_team_id: int | None,
    away_team_id: int | None,
    max_meetings: int = 10,
) -> dict[str, Any]:
    rows = safe_list(meetings)[:max_meetings]
    if not rows or home_team_id is None:
        return {
            "meetings_used": 0,
            "home_win_pct": None,
            "goals_home_avg": None,
            "goals_away_avg": None,
            "btts_pct": None,
            "over_2_5_pct": None,
            "explanation": ["No head-to-head meetings available."],
        }

    home_w = away_w = draws = btts = over25 = 0.0
    home_goals = away_goals = 0.0
    weight_sum = 0.0
    used = 0
    ref = parse_kickoff((rows[0].get("fixture") or {}).get("date")) if rows else None

    for item in rows:
        side = team_side_in_fixture(item, home_team_id)
        if side is None:
            continue
        home_g, away_g = goals_from_fixture(item)
        if home_g is None or away_g is None:
            continue
        kickoff = parse_kickoff((item.get("fixture") or {}).get("date"))
        w = recency_weight(years_since(kickoff, reference=ref))
        weight_sum += w
        used += 1
        if side == "home":
            hg, ag = home_g, away_g
        else:
            hg, ag = away_g, home_g
        home_goals += hg * w
        away_goals += ag * w
        if hg > ag:
            home_w += w
        elif ag > hg:
            away_w += w
        else:
            draws += w
        if hg > 0 and ag > 0:
            btts += w
        if hg + ag > 2:
            over25 += w

    if weight_sum <= 0:
        return {
            "meetings_used": 0,
            "explanation": ["H2H rows present but no completed scores parsed."],
        }

    home_win_pct = round(home_w / weight_sum * 100, 1)
    detail = {
        "meetings_used": used,
        "home_win_pct": home_win_pct,
        "away_win_pct": round(away_w / weight_sum * 100, 1),
        "draw_pct": round(draws / weight_sum * 100, 1),
        "goals_home_avg": round(home_goals / weight_sum, 2),
        "goals_away_avg": round(away_goals / weight_sum, 2),
        "btts_pct": round(btts / weight_sum * 100, 1),
        "over_2_5_pct": round(over25 / weight_sum * 100, 1),
        "explanation": [
            f"Weighted last {used} H2H meetings: home win {home_win_pct}%, "
            f"avg score {round(home_goals/weight_sum,1)}-{round(away_goals/weight_sum,1)}."
        ],
    }
    return detail


def national_h2h_score(
    meetings: list[dict[str, Any]] | None,
    *,
    home_team_id: int | None,
    away_team_id: int | None,
) -> tuple[float, dict[str, Any]]:
    detail = build_h2h_detail(meetings, home_team_id=home_team_id, away_team_id=away_team_id)
    used = int(detail.get("meetings_used") or 0)
    if used == 0:
        return 50.0, detail

    home_win = float(detail.get("home_win_pct") or 33)
    goal_edge = float(detail.get("goals_home_avg") or 1.0) - float(detail.get("goals_away_avg") or 1.0)
    decisiveness = abs(home_win - float(detail.get("away_win_pct") or 33))
    score = clamp(50 + decisiveness * 0.25 + goal_edge * 8, 30, 88)
    return round(score, 1), detail
