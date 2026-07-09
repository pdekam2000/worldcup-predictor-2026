"""MCP odds freshness and refresh tools."""

from __future__ import annotations

from worldcup_predictor.mcp_server.policies import MAX_AUDIT_FIXTURES, MAX_REFRESH_FIXTURES, validate_fixture_id_list
from worldcup_predictor.mcp_server import runtime


def odds_freshness_audit(fixture_ids: list[int]) -> dict[str, object]:
    ids = validate_fixture_id_list(fixture_ids, max_count=MAX_AUDIT_FIXTURES, label="fixture_ids")
    rows = runtime.odds_freshness_audit(ids)
    return {"fixtures": rows, "count": len(rows)}


def refresh_stale_odds(fixture_ids: list[int]) -> dict[str, object]:
    ids = validate_fixture_id_list(fixture_ids, max_count=MAX_REFRESH_FIXTURES, label="fixture_ids")
    rows = runtime.refresh_stale_odds(ids)
    return {"fixtures": rows, "count": len(rows)}
