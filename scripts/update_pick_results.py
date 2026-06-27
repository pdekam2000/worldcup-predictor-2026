"""
Update daily picks results after matches finish.
Run after matches are done to mark won/lost.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, ".")

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings


def actual_result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def update_picks(target_date: str | None = None) -> None:
    d = target_date or str(date.today())
    path = Path(f"artifacts/daily_picks_{d}.json")

    if not path.exists():
        print(f"No picks file for {d}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    picks = data.get("picks", [])

    if not picks:
        print("No picks to update")
        return

    settings = get_settings()
    client = ApiFootballClient(settings)

    # get results from API
    result = client._safe_get(
        "fixtures",
        {"date": d, "league": "1", "season": "2026"},
        placeholder_factory=lambda: None,
        ttl_seconds=60,
    )

    # build results index
    results_index: dict[int, dict] = {}
    if result and result.data:
        for f in result.data:
            fid = f["fixture"]["id"]
            status = f["fixture"]["status"]["short"]
            hg = f["goals"]["home"]
            ag = f["goals"]["away"]
            if status == "FT" and hg is not None and ag is not None:
                results_index[fid] = {
                    "home_goals": hg,
                    "away_goals": ag,
                    "actual": actual_result(hg, ag),
                    "score": f"{hg}-{ag}",
                }

    # also check Bundesliga + PL
    for league_id in [78, 39]:
        res2 = client._safe_get(
            "fixtures",
            {"date": d, "league": str(league_id), "season": "2025"},
            placeholder_factory=lambda: None,
            ttl_seconds=60,
        )
        if res2 and res2.data:
            for f in res2.data:
                fid = f["fixture"]["id"]
                status = f["fixture"]["status"]["short"]
                hg = f["goals"]["home"]
                ag = f["goals"]["away"]
                if status == "FT" and hg is not None and ag is not None:
                    results_index[fid] = {
                        "home_goals": hg,
                        "away_goals": ag,
                        "actual": actual_result(hg, ag),
                        "score": f"{hg}-{ag}",
                    }

    # update picks
    updated = 0
    for pick in picks:
        fid = pick.get("fixture_id")
        if not fid or pick.get("result") not in (None, "pending"):
            continue

        match_result = results_index.get(fid)
        if not match_result:
            continue

        actual = match_result["actual"]
        predicted = pick.get("selection", "")
        pick["result"] = "won" if actual == predicted else "lost"
        pick["score"] = match_result["score"]
        pick["actual"] = actual
        updated += 1

        print(f"{pick['home']} vs {pick['away']}: {match_result['score']} | "
              f"Pick={predicted} | Result={'✅ WON' if pick['result']=='won' else '❌ LOST'}")

    # save
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nUpdated {updated} picks → {path}")

    # summary
    won = sum(1 for p in picks if p.get("result") == "won")
    lost = sum(1 for p in picks if p.get("result") == "lost")
    pending = sum(1 for p in picks if p.get("result") in (None, "pending"))
    print(f"Summary: {won}W / {lost}L / {pending} pending")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    update_picks(target)
