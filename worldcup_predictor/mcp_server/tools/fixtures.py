"""MCP fixture resolution tools."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.mcp_server.policies import (
    MAX_RESOLVE_MATCHES,
    validate_iso_date,
    validate_team_name,
)
from worldcup_predictor.mcp_server import runtime


def resolve_fixtures(matches: list[dict[str, Any]]) -> dict[str, Any]:
    if len(matches) > MAX_RESOLVE_MATCHES:
        raise ValueError(f"matches exceeds maximum of {MAX_RESOLVE_MATCHES}")
    normalized: list[dict[str, str]] = []
    for item in matches:
        normalized.append(
            {
                "home_team": validate_team_name(item.get("home_team"), field="home_team"),
                "away_team": validate_team_name(item.get("away_team"), field="away_team"),
                "date": validate_iso_date(str(item.get("date"))).isoformat(),
            }
        )
    results = runtime.resolve_fixtures(normalized)
    return {"matches": results, "count": len(results)}
