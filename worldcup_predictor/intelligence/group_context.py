"""Extract group / standings context for a fixture."""

from __future__ import annotations

import re
from typing import Any


def _match_team(row: dict[str, Any], team_id: int | None, team_name: str) -> bool:
    team = row.get("team") or {}
    if team_id and team.get("id") == team_id:
        return True
    return str(team.get("name", "")).lower() == team_name.lower()


def _row_summary(row: dict[str, Any]) -> dict[str, Any]:
    team = row.get("team") or {}
    group = row.get("group") or ""
    return {
        "team": team.get("name"),
        "group": group,
        "rank": row.get("rank"),
        "points": row.get("points"),
        "played": row.get("all", {}).get("played") if isinstance(row.get("all"), dict) else row.get("played"),
        "goal_diff": row.get("goalsDiff"),
        "form": row.get("form"),
        "description": row.get("description") or row.get("status") or "",
    }


def extract_group_context(
    standings_blocks: list[dict[str, Any]],
    *,
    home_team_id: int | None,
    away_team_id: int | None,
    home_team: str,
    away_team: str,
    stage: str | None = None,
) -> dict[str, Any]:
    home_ctx: dict[str, Any] | None = None
    away_ctx: dict[str, Any] | None = None

    for block in standings_blocks:
        league = block.get("league") or {}
        group_name = league.get("group") or league.get("name") or ""
        standings_groups = block.get("standings") or []
        for group_rows in standings_groups:
            if not isinstance(group_rows, list):
                continue
            for row in group_rows:
                if not isinstance(row, dict):
                    continue
                summary = _row_summary(row)
                if not summary.get("group") and group_name:
                    summary["group"] = group_name
                if _match_team(row, home_team_id, home_team):
                    home_ctx = summary
                if _match_team(row, away_team_id, away_team):
                    away_ctx = summary

    parsed_group = _group_from_stage(stage)
    ctx: dict[str, Any] = {
        "available": bool(home_ctx or away_ctx or (stage and stage != "TBD")),
        "round": stage if stage and stage != "TBD" else None,
        "stage": stage or "TBD",
        "home": home_ctx or {"team": home_team, "rank": None, "points": None, "group": parsed_group},
        "away": away_ctx or {"team": away_team, "rank": None, "points": None, "group": parsed_group},
    }
    if home_ctx and home_ctx.get("group"):
        ctx["group"] = home_ctx["group"]
    elif away_ctx and away_ctx.get("group"):
        ctx["group"] = away_ctx["group"]
    elif parsed_group:
        ctx["group"] = parsed_group
    else:
        ctx["group"] = stage if stage and stage != "TBD" else None
    return ctx


def _group_from_stage(stage: str | None) -> str | None:
    if not stage or stage == "TBD":
        return None
    letter = re.search(r"Group\s+([A-H])\b", stage, re.IGNORECASE)
    if letter:
        return f"Group {letter.group(1).upper()}"
    if "Group Stage" in stage or "Round" in stage or "Final" in stage:
        return stage
    if "Group" in stage and len(stage) <= 24:
        return stage
    return None
