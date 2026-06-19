"""Phase 8 live specialist audit for one fixture — compares specialist statuses."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import runpy

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

FIXTURE_ID = 1489388
BASE = "http://127.0.0.1:8000"
FORCE_REFRESH = "--refresh" in sys.argv[1:]

TARGET_AGENTS = (
    "injury",
    "injury_suspension_intelligence_agent",
    "lineup",
    "lineup_intelligence_agent",
    "player_quality",
    "tactics",
    "xg_chance_quality_intelligence_agent",
    "master_analysis_agent",
)


def _req(method: str, path: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode())
        except Exception:
            return exc.code, {"detail": exc.read().decode()[:300]}


def _agent_rows(payload: dict) -> dict[str, dict]:
    return (payload.get("specialist_summary") or {}).get("agents") or {}


def _pick_status(agents: dict[str, dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, row in agents.items():
        for target in TARGET_AGENTS:
            if target in key or key == target:
                out[key] = str(row.get("status") or "—")
    return out


def main() -> int:
    print(f"=== Phase 8 Sportmonks consumption audit fixture {FIXTURE_ID} ===")
    code, health = _req("GET", "/api/health")
    print(f"health: {code} {health.get('status')}")

    code, cached = _req("GET", f"/api/predict/{FIXTURE_ID}")
    before = cached if cached.get("status") == "ok" else {}
    before_agents = _pick_status(_agent_rows(before))
    print("BEFORE (cached payload if any):")
    for name, status in sorted(before_agents.items()):
        print(f"  {name}: {status}")
    if not before_agents:
        print("  (no cached prediction — before state unavailable)")

    path = f"/api/predict/{FIXTURE_ID}"
    if FORCE_REFRESH:
        path += "?force_refresh=true"
    code, after = _req("POST", path)
    print(f"POST predict: {code} cache_source={after.get('cache_source')}")
    after_agents = _pick_status(_agent_rows(after))
    print("AFTER:")
    for name, status in sorted(after_agents.items()):
        print(f"  {name}: {status}")

    signals = (after.get("data_signals") or {})
    print(f"data_quality: {after.get('data_quality')}")
    print(f"data_signals: {signals}")

    from worldcup_predictor.config.settings import Settings

    settings = Settings()
    print(f"sportmonks_configured: {settings.sportmonks_configured}")

    ok = after.get("status") == "ok"
    return 0 if ok else 1


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        if arg.startswith("http"):
            BASE = arg
        elif arg.isdigit():
            FIXTURE_ID = int(arg)
    raise SystemExit(main())
