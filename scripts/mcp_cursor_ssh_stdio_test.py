#!/usr/bin/env python3
"""Simulate Cursor MCP over SSH stdio (same transport Cursor uses)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-host", default="root@91.107.188.229")
    parser.add_argument("--output", default="artifacts/mcp_cursor_ssh_stdio_report.json")
    args = parser.parse_args()

    remote_cmd = (
        "cd /opt/worldcup-predictor && set -a && source .env.production && set +a && "
        "PYTHONPATH=/opt/worldcup-predictor .venv/bin/python -m worldcup_predictor.mcp_server.server --stdio"
    )

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command="ssh", args=["-T", args.ssh_host, remote_cmd])
    report: dict = {"transport": "ssh-stdio", "ssh_host": args.ssh_host, "calls": {}}

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            report["tool_count"] = len(tools.tools)

            async def call(name: str, arguments: dict | None = None):
                result = await session.call_tool(name, arguments or {})
                text = result.content[0].text if result.content else "{}"
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = text
                report["calls"][name] = {"ok": not result.isError, "payload": payload}

            await call("server_health")
            await call("model_status")
            await call(
                "resolve_fixtures",
                {"matches": [{"home_team": "Qarabag", "away_team": "Vestri", "date": "2026-07-09"}]},
            )
            await call("odds_freshness_audit", {"fixture_ids": [1554444]})

    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    ok = all(c.get("ok") for c in report["calls"].values())
    print(json.dumps({"ok": ok, "output": str(out), "tool_count": report["tool_count"]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
