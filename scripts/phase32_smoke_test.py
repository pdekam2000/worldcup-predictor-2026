#!/usr/bin/env python3
"""Production smoke test for Phase 32B+32C+32E deploy."""
from __future__ import annotations

import json
import sys
import urllib.request

FIXTURES = [
    (1539007, "Netherlands vs Sweden"),
    (1489393, "Germany vs Ivory Coast"),
    (1489400, "France vs Senegal"),  # fallback if wrong
]


def predict(fid: int) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/predict/{fid}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def extract(d: dict) -> dict:
    nat = (d.get("national_team_intelligence") or d.get("supplemental") or {})
    if not nat and isinstance(d.get("data_signals"), dict):
        nat = d.get("data_signals", {}).get("national_team_intelligence") or {}
    # Try nested paths
    for key in ("national_team_intelligence",):
        if key in d:
            nat = d[key] if isinstance(d[key], dict) else nat
    return {
        "fixture_id": d.get("fixture_id"),
        "match": f"{d.get('home_team')} vs {d.get('away_team')}",
        "confidence": d.get("confidence"),
        "no_bet": d.get("no_bet"),
        "safe_pick": d.get("safe_pick"),
        "value_pick": d.get("value_pick"),
        "aggressive_pick": d.get("aggressive_pick"),
        "national_form_score": nat.get("national_form_score"),
        "national_h2h_score": nat.get("national_h2h_score"),
        "injury_impact_score": nat.get("injury_impact_score"),
        "consensus_strength_score": nat.get("consensus_strength_score"),
        "version": nat.get("version"),
        "status": d.get("status"),
    }


def main() -> int:
    results = []
    for fid, label in FIXTURES:
        try:
            d = predict(fid)
            row = extract(d)
            row["label"] = label
            results.append(row)
            print(json.dumps(row, indent=2))
        except Exception as exc:
            print(json.dumps({"fixture_id": fid, "label": label, "error": str(exc)}))
            results.append({"fixture_id": fid, "error": str(exc)})

    # Find any no_bet=false fixture
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        rows = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=25)
        for r in rows:
            fid = int(r["fixture_id"])
            if fid in {x[0] for x in FIXTURES}:
                continue
            d = predict(fid)
            if not d.get("no_bet", True):
                row = extract(d)
                row["label"] = "no_bet=false sample"
                results.append(row)
                print(json.dumps(row, indent=2))
                break
    except Exception as exc:
        print(json.dumps({"extra_fixture_search": str(exc)}))

    out_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/phase32_smoke_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {out_path}")
    ok = sum(1 for r in results if r.get("status") == "ok" or r.get("confidence") is not None)
    print(f"SMOKE_OK={ok}/{len(results)}")
    return 0 if ok >= 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
