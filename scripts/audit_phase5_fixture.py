"""Audit Phase 5 specialist statuses for one fixture — no secrets logged."""

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
FORCE_REFRESH = False
for arg in sys.argv[1:]:
    if arg == "--refresh":
        FORCE_REFRESH = True
    elif arg.startswith("http"):
        BASE = arg
    else:
        try:
            FIXTURE_ID = int(arg)
        except ValueError:
            pass


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


def main() -> int:
    print(f"=== Phase 5 audit fixture {FIXTURE_ID} ===")
    code, health = _req("GET", "/api/health")
    print(f"health: {code} {health.get('status')}")

    code, cached = _req("GET", f"/api/predict/{FIXTURE_ID}")
    print(f"GET predict: {code} cache_source={cached.get('cache_source', cached.get('detail', {}).get('status'))}")

    code, post1 = _req("POST", f"/api/predict/{FIXTURE_ID}")
    print(f"POST predict #1: {code} cache_source={post1.get('cache_source')}")

    code, post2 = _req("POST", f"/api/predict/{FIXTURE_ID}")
    print(f"POST predict #2: {code} cache_source={post2.get('cache_source')}")

    if FORCE_REFRESH:
        code, fresh = _req("POST", f"/api/predict/{FIXTURE_ID}?force_refresh=true")
        print(f"POST force_refresh: {code} cache_source={fresh.get('cache_source')}")
        payload = fresh
    else:
        payload = post1 if post1.get("status") == "ok" else post2
    agents = (payload.get("specialist_summary") or {}).get("agents") or {}
    print("specialists:")
    for name in sorted(agents):
        row = agents[name]
        print(
            f"  {name}: status={row.get('status')} "
            f"reason={row.get('status_reason')} impact={row.get('impact_score')}"
        )

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.clients.api_football import ApiFootballClient

    settings = get_settings()
    print(f"sportmonks_configured: {settings.sportmonks_configured}")
    print(f"weather_configured: {settings.weather_provider_configured}")

    api = ApiFootballClient(settings)
    skip = api.get_injuries(FIXTURE_ID, league_id=0)
    print(f"injuries_league_0_skip: {skip.skip_reason} source={skip.source}")

    code, _ = _req("GET", "/api/admin/quota")
    print(f"admin_quota_no_auth: {code} (expect 401)")

    ok = post1.get("status") == "ok" or post2.get("status") == "ok"
    cache_ok = post2.get("cache_source") == "cache" or post1.get("cache_source") == "cache"
    print(f"prediction_ok: {ok}")
    print(f"cache_protection_ok: {cache_ok}")
    return 0 if ok and cache_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
