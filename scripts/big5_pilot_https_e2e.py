#!/usr/bin/env python3
"""HTTPS E2E — Big 5 Tier B onboarding (per-league pilot dates)."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.environ.get("GPT_ACTIONS_BASE_URL", "https://footballpredictor.it.com/api/gpt-actions/v1")
KEY = os.environ.get("GPT_ACTIONS_API_KEY", "")
PILOT_DATES = {
    "la_liga": "2026-08-16",
    "serie_a": "2026-08-22",
    "ligue_1": "2026-08-22",
}


def get(path: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    if not KEY:
        print("missing GPT_ACTIONS_API_KEY", file=sys.stderr)
        return 1
    out = {"leagues": {}, "pass": {}}
    for key, date in PILOT_DATES.items():
        listing = get(f"/matches/list?date={date}&timezone=Europe/Vienna&listing_filter=all")
        prod = get(f"/matches/discover?date={date}&timezone=Europe/Vienna&scope=production")
        rows = [m for m in listing.get("matches") or [] if m.get("competition") == key]
        out["leagues"][key] = {
            "date": date,
            "list_count": len(rows),
            "sample": rows[:1],
            "test_phase": (rows[0].get("display_status") == "TEST_PHASE") if rows else False,
            "production_excluded": all(m.get("competition") != key for m in prod.get("matches") or []),
        }
        out["pass"][key] = (
            len(rows) >= 1
            and out["leagues"][key]["test_phase"]
            and out["leagues"][key]["production_excluded"]
        )
    print(json.dumps(out, indent=2))
    return 0 if all(out["pass"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
