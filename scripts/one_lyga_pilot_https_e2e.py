#!/usr/bin/env python3
"""HTTPS E2E — 1 Lyga Tier B pilot."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

DATE = "2026-07-18"
BASE = os.environ.get("GPT_ACTIONS_BASE_URL", "https://footballpredictor.it.com/api/gpt-actions/v1")
KEY = os.environ.get("GPT_ACTIONS_API_KEY", "")


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
    listing = get(f"/matches/list?date={DATE}&timezone=Europe/Vienna&listing_filter=all")
    owner = get(f"/matches/discover?date={DATE}&timezone=Europe/Vienna&scope=owner")
    prod = get(f"/matches/discover?date={DATE}&timezone=Europe/Vienna&scope=production")
    shadow = get(f"/matches/discover?date={DATE}&timezone=Europe/Vienna&scope=shadow")
    one = [
        m
        for m in listing.get("matches") or []
        if m.get("competition") == "one_lyga" or "league_361" in str(m.get("competition_raw") or "")
    ]
    out = {
        "date": DATE,
        "list_count": listing.get("count"),
        "one_lyga_list_count": len(one),
        "one_lyga_sample": one[:2],
        "discover_owner_count": owner.get("count"),
        "discover_owner_tier_b": owner.get("tier_b_count"),
        "discover_production_count": prod.get("count"),
        "discover_shadow_count": shadow.get("count"),
        "pass": {
            "one_lyga_listed": len(one) >= 1,
            "test_phase_label": (one[0].get("display_status") == "TEST_PHASE") if one else False,
            "production_excludes_one_lyga": all(
                m.get("competition") != "one_lyga" for m in prod.get("matches") or []
            ),
        },
    }
    print(json.dumps(out, indent=2))
    ok = out["pass"]["one_lyga_listed"] and out["pass"]["test_phase_label"] and out["pass"]["production_excludes_one_lyga"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
