#!/usr/bin/env python3
"""Probe production payloads for HOTFIX H4."""
import json
import sys
import urllib.request

FIXTURES = [1489409, 1489410]


def get(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    for fid in FIXTURES:
        print(f"\n=== fixture {fid} ===")
        for path in [
            f"/api/predict/{fid}",
            f"/api/predict/{fid}?competition=league_1",
            f"/api/predops/snapshots/latest?fixture_id={fid}",
        ]:
            try:
                d = get(base + path)
                if "snapshot" in d:
                    d = d["snapshot"]
                overlay = d.get("publication_overlay") or {}
                pbp = overlay.get("public_best_pick")
                print(path)
                print("  cache_source:", d.get("cache_source"))
                print("  public_best_pick type:", type(pbp).__name__, str(pbp)[:120])
                print("  prediction type:", type(d.get("prediction")).__name__, str(d.get("prediction"))[:120])
                print("  home_team_logo:", d.get("home_team_logo"))
                print("  away_team_logo:", d.get("away_team_logo"))
            except Exception as e:
                print(path, "ERR", e)

    try:
        m = get(base + "/api/matches?competition=all&include_summary=true&page_size=30")
        rows = m.get("matches") or []
        with_logo = sum(1 for r in rows if r.get("home_team_logo") or r.get("away_team_logo"))
        print(f"\n=== matches list: {len(rows)} rows, {with_logo} with any logo ===")
        for r in rows[:5]:
            print(
                r.get("fixture_id"),
                r.get("home_team"),
                r.get("home_team_logo"),
                "|",
                r.get("away_team_logo"),
            )
    except Exception as e:
        print("matches ERR", e)


if __name__ == "__main__":
    main()
