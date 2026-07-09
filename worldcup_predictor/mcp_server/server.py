"""WorldCup Predictor MCP server — approved tools only."""

from __future__ import annotations

import argparse
import json
import sys
import time
from functools import wraps
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from worldcup_predictor.mcp_server.audit import AuditLogger
from worldcup_predictor.mcp_server.config import load_mcp_config
from worldcup_predictor.mcp_server.policies import APPROVED_TOOLS, MCP_VERSION
from worldcup_predictor.mcp_server.tools import fixtures, health, odds, predictions, reports
from worldcup_predictor.mcp_server import runtime


def _build_server(config) -> FastMCP:
    mcp = FastMCP(
        "WorldCup Predictor MCP",
        instructions=(
            "Controlled owner prediction bridge. Resolves fixtures, audits/refreshes odds, "
            "runs canonical WDE and ECSE, returns structured evidence. No shell, SQL, or file access."
        ),
        host=config.host,
        port=config.port,
    )
    audit = AuditLogger(config.audit_log_path)

    def audited(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            fixture_count = None
            if name in ("odds_freshness_audit", "refresh_stale_odds", "run_batch_predictions"):
                fixture_count = len(kwargs.get("fixture_ids") or args[0] if args else [])
            elif name == "run_fixture_prediction":
                fixture_count = 1
            elif name == "resolve_fixtures":
                fixture_count = len(kwargs.get("matches") or args[0] if args else [])
            try:
                result = fn(*args, **kwargs)
                status = None
                if isinstance(result, dict):
                    status = (result.get("quality") or {}).get("status") or result.get("status")
                audit.write(
                    tool_name=name,
                    caller_mode=config.caller_mode,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    success=True,
                    fixture_count=fixture_count,
                    result_status=str(status) if status else None,
                )
                return result
            except Exception as exc:
                audit.write(
                    tool_name=name,
                    caller_mode=config.caller_mode,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    success=False,
                    fixture_count=fixture_count,
                    error=str(exc),
                )
                raise

        return wrapper

    @mcp.tool(name="server_health")
    def server_health() -> dict[str, Any]:
        """Return sanitized host, service, database, and MCP health."""
        return audited("server_health", health.server_health)()

    @mcp.tool(name="model_status")
    def model_status() -> dict[str, Any]:
        """Return WDE/ECSE availability and canonical pipeline readiness."""
        return audited("model_status", runtime.model_status)()

    @mcp.tool(name="resolve_fixtures")
    def resolve_fixtures(matches: list[dict[str, Any]]) -> dict[str, Any]:
        """Resolve home/away/date tuples to internal fixture IDs."""
        return audited("resolve_fixtures", fixtures.resolve_fixtures)(matches)

    @mcp.tool(name="odds_freshness_audit")
    def odds_freshness_audit(fixture_ids: list[int]) -> dict[str, Any]:
        """Audit canonical odds freshness for up to 20 fixtures."""
        return audited("odds_freshness_audit", odds.odds_freshness_audit)(fixture_ids)

    @mcp.tool(name="refresh_stale_odds")
    def refresh_stale_odds(fixture_ids: list[int]) -> dict[str, Any]:
        """Strict live refresh via API-Football → Sportmonks → OddAlerts crosswalk."""
        return audited("refresh_stale_odds", odds.refresh_stale_odds)(fixture_ids)

    @mcp.tool(name="run_fixture_prediction")
    def run_fixture_prediction(fixture_id: int, refresh_if_stale: bool = True) -> dict[str, Any]:
        """Run canonical WDE + ECSE for one fixture when odds are fresh."""
        return audited("run_fixture_prediction", predictions.run_fixture_prediction)(
            fixture_id, refresh_if_stale=refresh_if_stale
        )

    @mcp.tool(name="run_batch_predictions")
    def run_batch_predictions(fixture_ids: list[int], refresh_if_stale: bool = True) -> dict[str, Any]:
        """Batch canonical predictions (max 10), isolated per fixture."""
        return audited("run_batch_predictions", predictions.run_batch_predictions)(
            fixture_ids, refresh_if_stale=refresh_if_stale
        )

    @mcp.tool(name="latest_prediction_report")
    def latest_prediction_report() -> dict[str, Any]:
        """Return latest owner report from reports/owner/."""
        return audited("latest_prediction_report", reports.latest_prediction_report)()

    @mcp.tool(name="prediction_report_by_date")
    def prediction_report_by_date(date: str) -> dict[str, Any]:
        """Return owner report for YYYY-MM-DD from approved report directory."""
        return audited("prediction_report_by_date", reports.prediction_report_by_date)(date)

    @mcp.tool(name="provider_status")
    def provider_status() -> dict[str, Any]:
        """Safe provider configuration status without secrets."""
        return audited("provider_status", runtime.provider_status)()

    return mcp


def dry_test() -> dict[str, Any]:
    config = load_mcp_config(dry_test=True)
    _build_server(config)
    names = sorted(APPROVED_TOOLS)
    return {
        "mcp_version": MCP_VERSION,
        "transport": config.transport,
        "host": config.host,
        "bind_localhost_only": config.bind_localhost_only,
        "approved_tools": names,
        "tool_count": len(names),
        "fastmcp_tools_registered": len(names),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WorldCup Predictor MCP server")
    parser.add_argument("--stdio", action="store_true", help="Run with stdio transport (default)")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="Transport mode (default: stdio or MCP_TRANSPORT)",
    )
    parser.add_argument("--dry-test", action="store_true", help="Import server and print tool manifest")
    args = parser.parse_args(argv)

    if args.dry_test:
        print(json.dumps(dry_test(), indent=2))
        return 0

    transport = args.transport or ("stdio" if args.stdio or not args.transport else None)
    config = load_mcp_config(transport=transport)
    mcp = _build_server(config)
    mode = config.transport if not transport else transport
    if mode == "stdio" or args.stdio:
        mcp.run(transport="stdio")
    elif mode == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
