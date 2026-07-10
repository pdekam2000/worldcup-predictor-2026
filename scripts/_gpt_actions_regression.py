#!/usr/bin/env python3
"""Production GPT Actions read-only regression."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request


def _load_env(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    env = _load_env("/etc/worldcup-gpt-actions/environment")
    base = f"http://{env['GPT_ACTIONS_HOST']}:{env['GPT_ACTIONS_PORT']}/api/gpt-actions/v1"
    token = env["GPT_ACTIONS_API_KEY"]
    results: dict = {}
    results["status"] = get(f"{base}/system/status", token)
    listing = get(f"{base}/matches/list?date=2026-07-12&listing_filter=all", token)
    results["list_all"] = {
        "mode": listing.get("mode"),
        "count": listing.get("count"),
        "tier_a": listing.get("tier_a_count"),
        "tier_b": listing.get("tier_b_count"),
    }
    owner = get(f"{base}/matches/discover?date=2026-07-12&scope=owner", token)
    results["discover_owner"] = {
        "scope": owner.get("scope"),
        "count": owner.get("count"),
        "tier_a": owner.get("tier_a_count"),
        "tier_b": owner.get("tier_b_count"),
    }
    prod = get(f"{base}/matches/discover?date=2026-07-12&scope=production", token)
    results["discover_production"] = {"scope": prod.get("scope"), "count": prod.get("count")}
    trusted = get(f"{base}/matches/list?date=2026-07-12&listing_filter=trusted", token)
    results["list_trusted"] = {"count": trusted.get("count"), "filter": trusted.get("listing_filter")}
    test_phase = get(f"{base}/matches/list?date=2026-07-12&listing_filter=test_phase", token)
    results["list_test_phase"] = {"count": test_phase.get("count"), "filter": test_phase.get("listing_filter")}
    if listing.get("matches"):
        sample = listing["matches"][0]
        results["sample_labels"] = {
            "display_status": sample.get("display_status"),
            "display_label": sample.get("display_label"),
            "listing_status": sample.get("listing_status"),
        }
    print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
