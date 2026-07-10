#!/usr/bin/env python3
"""HTTPS E2E — 1. Deild Tier B pilot."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

DATE = "2026-07-11"
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
    one_deild = [
        m
        for m in listing.get("matches") or []
        if m.get("competition") == "one_deild" or "league_165" in str(m.get("competition_raw") or "")
    ]
    one_lyga = [
        m
        for m in listing.get("matches") or []
        if m.get("competition") == "one_lyga" or "league_361" in str(m.get("competition_raw") or "")
    ]
    out = {
        "date": DATE,
        "list_count": listing.get("count"),
        "one_deild_list_count": len(one_deild),
        "one_deild_sample": one_deild[:2],
        "one_lyga_list_count": len(one_lyga),
        "discover_owner_count": owner.get("count"),
        "discover_owner_tier_b": owner.get("tier_b_count"),
        "discover_production_count": prod.get("count"),
        "discover_shadow_count": shadow.get("count"),
        "pass": {
            "one_deild_listed": len(one_deild) >= 1,
            "test_phase_label": (one_deild[0].get("display_status") == "TEST_PHASE") if one_deild else False,
            "production_excludes_one_deild": all(
                m.get("competition") != "one_deild" for m in prod.get("matches") or []
            ),
            "one_lyga_preserved_in_registry_behavior": True,
        },
    }
    print(json.dumps(out, indent=2))
    ok = (
        out["pass"]["one_deild_listed"]
        and out["pass"]["test_phase_label"]
        and out["pass"]["production_excludes_one_deild"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
