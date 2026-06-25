"""Phase 49A production smoke — GUI routes and data visibility."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ROUTES = [
    "/",
    "/dashboard",
    "/matches",
    "/history",
    "/accuracy",
    "/subscription",
]


def _get(path: str) -> tuple[int, str]:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "text/html,application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read(500).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(200).decode("utf-8", errors="replace")


def main() -> int:
    print(f"Phase 49A smoke @ {BASE}")
    ok = 0
    for path in ROUTES:
        code, _ = _get(path)
        status = "OK" if code in (200, 301, 302, 307, 308) else "FAIL"
        if status == "OK":
            ok += 1
        print(f"  [{status}] GET {path} -> {code}")

    api_paths = [
        "/api/system/summary",
        "/api/matches?status=all&page=1&page_size=10",
        "/api/performance/summary",
        "/api/health",
    ]
    for path in api_paths:
        code, body = _get(path)
        status = "OK" if code == 200 else "FAIL"
        if status == "OK":
            ok += 1
        detail = ""
        if path.startswith("/api/matches") and code == 200:
            try:
                data = json.loads(body) if body.startswith("{") else {}
                detail = f" total={data.get('total_count')}"
            except json.JSONDecodeError:
                pass
        print(f"  [{status}] GET {path} -> {code}{detail}")

    total = len(ROUTES) + len(api_paths)
    print(f"\nSmoke: {ok}/{total} OK")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
