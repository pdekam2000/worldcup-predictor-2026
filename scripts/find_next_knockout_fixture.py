#!/usr/bin/env python3
"""Find next upcoming WC knockout fixture — read-only DB scan."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, is_knockout_match, is_low_priority_match
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists

PHASE = "NEXT-KNOCKOUT-FRESH-ODDS-1"
UPCOMING = ("NS", "TBD", "TIMED", "SCHEDULED", "NOT_STARTED")
COMP_KEYS = {"wc": "world_cup_2026", "world_cup_2026": "world_cup_2026"}


def _knockout_label(round_name: str | None, status: str | None) -> str:
    if is_knockout_match(round_name=round_name, status=status):
        return "KNOCKOUT"
    if round_name and str(round_name).strip():
        return "KNOCKOUT_UNKNOWN"
    return "KNOCKOUT_UNKNOWN"


def find_upcoming_fixtures(
    *,
    db_path: str | None,
    competition_key: str,
    from_date: str,
    tz_name: str,
    limit: int,
) -> list[dict]:
    conn = connect_readonly(db_path)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    rows = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name, competition_key
        FROM fixtures
        WHERE competition_key = ?
          AND is_placeholder = 0
          AND UPPER(status) IN ('NS','TBD','TIMED','SCHEDULED','NOT_STARTED','NOT STARTED')
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc >= ?
        ORDER BY kickoff_utc ASC
        LIMIT ?
        """,
        (competition_key, now_iso, limit * 3),
    ).fetchall()

    out: list[dict] = []
    tz = ZoneInfo(tz_name)
    for row in rows:
        r = dict(row)
        fid = int(r["fixture_id"])
        ko_label = _knockout_label(r.get("round_name"), r.get("status"))

        has_wde = False
        if table_exists(conn, "worldcup_stored_predictions"):
            has_wde = bool(
                conn.execute(
                    "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
                    (fid,),
                ).fetchone()
            )
        has_ecse = False
        if table_exists(conn, "ecse_prediction_snapshots"):
            has_ecse = bool(
                conn.execute(
                    "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1",
                    (fid,),
                ).fetchone()
            )

        odds = _latest_odds(conn, fid)
        knockout = is_knockout_match(round_name=r.get("round_name"), status=r.get("status"))
        low_pri = is_low_priority_match(kickoff_utc=r.get("kickoff_utc"))
        cls = classify_odds_freshness(
            odds_snapshot_at=odds["snapshot_at"] if odds else None,
            knockout=knockout,
            low_priority=low_pri,
            odds_source=odds.get("source") if odds else None,
            has_odds=bool(odds),
        )

        kickoff_vienna = "—"
        if r.get("kickoff_utc"):
            try:
                dt = datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                kickoff_vienna = dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
            except ValueError:
                kickoff_vienna = str(r["kickoff_utc"])

        out.append(
            {
                "fixture_id": fid,
                "kickoff_utc": r.get("kickoff_utc"),
                "kickoff_vienna": kickoff_vienna,
                "competition": r.get("competition_key"),
                "stage_round": r.get("round_name") or "—",
                "knockout_classification": ko_label,
                "home_team": r.get("home_team"),
                "away_team": r.get("away_team"),
                "status": r.get("status"),
                "has_stored_prediction": has_wde,
                "has_ecse_snapshot": has_ecse,
                "latest_odds_snapshot_at": odds["snapshot_at"] if odds else None,
                "odds_source": odds.get("source") if odds else None,
                "odds_freshness_status": cls.status.value,
                "odds_age_hours": cls.odds_age_hours,
                "requires_fresh_odds": cls.requires_fresh_odds,
            }
        )

    conn.close()
    knockout_first = [x for x in out if x["knockout_classification"] == "KNOCKOUT"]
    unknown = [x for x in out if x["knockout_classification"] == "KNOCKOUT_UNKNOWN"]
    ordered = knockout_first + unknown
    return ordered[:limit]


def render_markdown(fixtures: list[dict], *, selected_id: int | None = None) -> str:
    lines = [
        "# Next Upcoming WC Fixtures",
        "",
        "| fixture_id | kickoff (Vienna) | stage | class | match | status | WDE | ECSE | odds_at | freshness | age_h |",
        "|-----------:|------------------|-------|-------|-------|--------|-----|------|---------|-----------|------:|",
    ]
    for f in fixtures:
        sel = " **" if f["fixture_id"] == selected_id else ""
        lines.append(
            f"|{sel}{f['fixture_id']}{sel}| {f['kickoff_vienna']} | {f['stage_round']} | {f['knockout_classification']} | "
            f"{f['home_team']} vs {f['away_team']} | {f['status']} | "
            f"{'yes' if f['has_stored_prediction'] else 'no'} | "
            f"{'yes' if f['has_ecse_snapshot'] else 'no'} | "
            f"{f['latest_odds_snapshot_at'] or '—'} | {f['odds_freshness_status']} | "
            f"{f['odds_age_hours'] if f['odds_age_hours'] is not None else '—'} |"
        )
    if selected_id:
        lines.extend(["", f"**Selected fixture_id:** {selected_id}", ""])
    return "\n".join(lines) + "\n"


def pick_next_knockout(fixtures: list[dict]) -> dict | None:
    for f in fixtures:
        if f["knockout_classification"] == "KNOCKOUT":
            return f
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Find next upcoming knockout WC fixture (read-only)")
    parser.add_argument("--competition", default="wc")
    parser.add_argument("--from-date", default="today")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()

    settings = get_settings()
    comp = COMP_KEYS.get(args.competition.lower(), args.competition)
    fixtures = find_upcoming_fixtures(
        db_path=args.db_path or settings.sqlite_path,
        competition_key=comp,
        from_date=args.from_date,
        tz_name=args.timezone,
        limit=args.limit,
    )
    selected = pick_next_knockout(fixtures)
    payload = {
        "phase": PHASE,
        "fixtures": fixtures,
        "selected_fixture": selected,
        "recommendation": "NO_UPCOMING_KNOCKOUT_FIXTURE" if not selected else "FIXTURE_FOUND",
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(render_markdown(fixtures, selected_id=selected["fixture_id"] if selected else None))
        if selected:
            print(f"Selected: {selected['home_team']} vs {selected['away_team']} (fixture_id={selected['fixture_id']})")
        else:
            print("NO_UPCOMING_KNOCKOUT_FIXTURE")

    return 0 if selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
