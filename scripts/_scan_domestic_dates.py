#!/usr/bin/env python3
"""Scan forward for proven domestic league fixture dates."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings

# Leagues with proven production runs in this project (DB + today_5 batch)
PROVEN_DOMESTIC_LEAGUE_IDS: dict[int, str] = {
    113: "allsvenskan",
    114: "superettan",
    362: "a_lyga",
    365: "virsliga",
    164: "urvalsdeild",
}

EXCLUDE_LEAGUE_IDS = {1, 2, 3, 848, 667, 10}
EXCLUDE_NAME_PARTS = (
    "world cup",
    "champions league",
    "europa league",
    "conference league",
    "friendly",
    "friendlies",
    "u20",
    "u19",
    "u17",
    "women",
    " w ",
    "reserve",
    "youth",
    "cup",
    "qualifying",
    "qualification",
)

NOT_STARTED = {"NS", "TBD", "SCHEDULED", "TIMED"}


def is_broad_domestic(item: dict) -> bool:
    league = item.get("league") or {}
    lid = int(league.get("id") or 0)
    name = str(league.get("name") or "").lower()
    country = str(league.get("country") or "").lower()
    if lid in EXCLUDE_LEAGUE_IDS:
        return False
    if any(x in name for x in EXCLUDE_NAME_PARTS):
        return False
    if country in ("world", "international", ""):
        return False
    fx = item.get("fixture") or {}
    st = str((fx.get("status") or {}).get("short") or "NS").upper()
    return st in NOT_STARTED


def main() -> None:
    settings = get_settings()
    client = ApiFootballClient(settings)
    out: list[dict] = []
    start = date(2026, 7, 8)
    for offset in range(0, 30):
        d = start + timedelta(days=offset)
        r = client._safe_get(
            "fixtures",
            {"date": d.isoformat()},
            placeholder_factory=lambda: None,
            ttl_seconds=60,
        )
        data = r.data if r and r.data else []
        proven = []
        broad = []
        for item in data:
            if not isinstance(item, dict):
                continue
            league = item.get("league") or {}
            lid = int(league.get("id") or 0)
            fx = item.get("fixture") or {}
            teams = item.get("teams") or {}
            st = str((fx.get("status") or {}).get("short") or "NS").upper()
            if st not in NOT_STARTED:
                continue
            row = {
                "fixture_id": fx.get("id"),
                "league_id": lid,
                "competition_key": PROVEN_DOMESTIC_LEAGUE_IDS.get(lid),
                "league_name": league.get("name"),
                "country": league.get("country"),
                "home": (teams.get("home") or {}).get("name"),
                "away": (teams.get("away") or {}).get("name"),
                "kickoff": fx.get("date"),
                "status": st,
            }
            if lid in PROVEN_DOMESTIC_LEAGUE_IDS:
                proven.append(row)
            elif is_broad_domestic(item):
                broad.append(row)
        out.append(
            {
                "date": d.isoformat(),
                "proven_domestic_count": len(proven),
                "broad_domestic_count": len(broad),
                "proven": proven,
                "broad_sample": broad[:5],
            }
        )
    Path("artifacts/domestic_league_date_scan.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for row in out:
        if row["proven_domestic_count"] >= 4:
            print("FIRST_4_PROVEN_DATE", row["date"], row["proven_domestic_count"])
            break
    else:
        for row in out:
            if row["proven_domestic_count"] > 0:
                print("PARTIAL", row["date"], row["proven_domestic_count"])


if __name__ == "__main__":
    main()
