"""Shared MCP response shapes (documentation helpers)."""

from __future__ import annotations

from typing import Any, TypedDict


class FixtureResolution(TypedDict, total=False):
    fixture_id: int | None
    home_team: str
    away_team: str
    kickoff_utc: str | None
    competition: str | None
    status: str | None
    resolution_method: str
    resolution_confidence: float | None
    ambiguous_candidates: list[dict[str, Any]]
