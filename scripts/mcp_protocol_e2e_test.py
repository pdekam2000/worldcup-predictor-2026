#!/usr/bin/env python3
"""MCP protocol end-to-end test (stdio transport)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXPECTED_TOOLS = frozenset(
    {
        "server_health",
        "model_status",
        "resolve_fixtures",
        "odds_freshness_audit",
        "refresh_stale_odds",
        "run_fixture_prediction",
        "run_batch_predictions",
        "latest_prediction_report",
        "prediction_report_by_date",
        "provider_status",
    }
)


def _close(a: float | None, b: float | None, tol: float = 0.01) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < tol


def _compare_prediction(mcp: dict[str, Any], direct: dict[str, Any]) -> dict[str, Any]:
    mismatches: list[str] = []
    m_wde = mcp.get("wde") or {}
    d_wde = direct.get("wde") or {}
    for key in ("home_probability", "draw_probability", "away_probability", "prediction", "confidence"):
        if m_wde.get(key) != d_wde.get(key) and not _close(m_wde.get(key), d_wde.get(key)):
            mismatches.append(f"wde.{key}: mcp={m_wde.get(key)} direct={d_wde.get(key)}")
    m_btts = mcp.get("btts") or {}
    d_btts = direct.get("btts") or {}
    if m_btts.get("prediction") != d_btts.get("prediction"):
        mismatches.append("btts.prediction")
    m_ou = mcp.get("over_under_2_5") or {}
    d_ou = direct.get("over_under_2_5") or {}
    if m_ou.get("prediction") != d_ou.get("prediction"):
        mismatches.append("ou25.prediction")
    m_scores = (mcp.get("ecse") or {}).get("top_scores") or []
    d_scores = (direct.get("ecse") or {}).get("top_scores") or []
    for i in range(min(5, len(m_scores), len(d_scores))):
        if m_scores[i].get("score") != d_scores[i].get("score"):
            mismatches.append(f"ecse.top{i+1}.score")
        if not _close(m_scores[i].get("probability"), d_scores[i].get("probability"), tol=0.0001):
            mismatches.append(f"ecse.top{i+1}.probability")
    return {"passed": not mismatches, "mismatches": mismatches, "tolerance": "probabilities ±0.01, ECSE ±0.0001"}


async def _run_stdio(command: list[str], *, env: dict[str, str] | None, tests: dict[str, Any]) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=command[0], args=command[1:], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            tests["list_tools"] = {
                "ok": names == EXPECTED_TOOLS,
                "count": len(names),
                "tools": sorted(names),
                "extra": sorted(names - EXPECTED_TOOLS),
                "missing": sorted(EXPECTED_TOOLS - names),
            }
            if names != EXPECTED_TOOLS:
                return 1

            async def call(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
                t0 = time.perf_counter()
                result = await session.call_tool(name, arguments or {})
                elapsed = int((time.perf_counter() - t0) * 1000)
                payload: Any = None
                if result.content:
                    block = result.content[0]
                    text = getattr(block, "text", None) or str(block)
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        payload = text
                return {"ok": not result.isError, "duration_ms": elapsed, "payload": payload}

            tests["calls"] = {}
            tests["calls"]["server_health"] = await call("server_health")
            tests["calls"]["model_status"] = await call("model_status")
            resolve_args = tests.get("resolve_args") or {
                "matches": [{"home_team": "Qarabag", "away_team": "Vestri", "date": "2026-07-09"}]
            }
            tests["calls"]["resolve_fixtures"] = await call("resolve_fixtures", resolve_args)
            fixture_id = tests.get("fixture_id")
            resolved = (tests["calls"]["resolve_fixtures"].get("payload") or {}).get("matches") or []
            if resolved and resolved[0].get("fixture_id"):
                fixture_id = int(resolved[0]["fixture_id"])
            if fixture_id is None:
                fixture_id = tests.get("fixture_id_fallback")
            if fixture_id:
                tests["calls"]["odds_freshness_audit"] = await call(
                    "odds_freshness_audit", {"fixture_ids": [int(fixture_id)]}
                )
            tests["calls"]["provider_status"] = await call("provider_status")

            if tests.get("run_prediction") and fixture_id:
                tests["calls"]["run_fixture_prediction"] = await call(
                    "run_fixture_prediction",
                    {"fixture_id": int(fixture_id), "refresh_if_stale": False},
                )
                from worldcup_predictor.mcp_server import runtime

                direct = runtime.run_fixture_prediction(int(fixture_id), refresh_if_stale=False)
                mcp_payload = tests["calls"]["run_fixture_prediction"].get("payload") or {}
                tests["parity"] = _compare_prediction(mcp_payload, direct)
                tests["parity"]["fixture_id"] = fixture_id

            if tests.get("run_batch") and tests.get("batch_fixture_ids"):
                tests["calls"]["run_batch_predictions"] = await call(
                    "run_batch_predictions",
                    {
                        "fixture_ids": tests["batch_fixture_ids"],
                        "refresh_if_stale": False,
                    },
                )
    return 0 if tests.get("list_tools", {}).get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdio-command", nargs=argparse.REMAINDER, help="Command to launch MCP stdio server")
    parser.add_argument("--fixture-id", type=int, default=1554444)
    parser.add_argument("--prediction", action="store_true")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--output", default="artifacts/mcp_protocol_e2e_report.json")
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    command = args.stdio_command or [
        sys.executable,
        "-m",
        "worldcup_predictor.mcp_server.server",
        "--stdio",
    ]

    tests: dict[str, Any] = {
        "transport": "stdio",
        "command": command,
        "fixture_id_fallback": args.fixture_id,
        "batch_fixture_ids": [args.fixture_id, 1554441, 1554406],
        "run_prediction": args.prediction,
        "run_batch": args.batch,
    }

    code = asyncio.run(_run_stdio(command, env=env, tests=tests))
    if args.prediction and tests.get("parity") and not tests["parity"].get("passed"):
        code = 2

    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(tests, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": code == 0, "output": str(out_path), "list_tools_ok": tests.get("list_tools", {}).get("ok")}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
