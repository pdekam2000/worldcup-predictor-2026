#!/usr/bin/env python3
"""Scheduled 1X2 odds refresh for today/tomorrow supported fixtures (no predictions)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope, fixture_allowed_for_discovery
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.odds.freshness_policy import should_refresh_odds
from worldcup_predictor.odds.refresh_gate import refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import discover_fixtures_from_db, vienna_day_utc_bounds

PHASE = "SCHEDULED-ODDS-REFRESH"


def _discover_refresh_candidates(
    *,
    target_dates: list[date],
    tz_name: str = "Europe/Vienna",
) -> list[dict]:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    keys = competition_keys_for_scope("owner")
    out: list[dict] = []
    try:
        for d in target_dates:
            start, end = vienna_day_utc_bounds(d, tz_name)
            fixtures = discover_fixtures_from_db(
                conn,
                competition_keys=keys,
                start_utc=start,
                end_utc=end,
            )
            for fx in fixtures:
                if not fixture_allowed_for_discovery(fx, "owner"):
                    continue
                row = {
                    "fixture_id": fx.fixture_id,
                    "competition_key": fx.competition_key,
                    "kickoff_utc": fx.kickoff_utc,
                    "home_team": fx.home_team,
                    "away_team": fx.away_team,
                    "status": fx.status,
                }
                meta = build_fixture_freshness_metadata(
                    conn,
                    fixture_id=int(fx.fixture_id),
                    kickoff_utc=fx.kickoff_utc,
                    round_name=None,
                    status=fx.status,
                )
                cls = {
                    "freshness_flag": meta.get("odds_freshness_status"),
                    "requires_fresh_odds": meta.get("requires_fresh_odds"),
                }
                hours_to_ko = None
                if fx.kickoff_utc:
                    ko = datetime.fromisoformat(str(fx.kickoff_utc).replace("Z", "+00:00"))
                    hours_to_ko = (ko.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600.0
                near_kickoff = hours_to_ko is not None and 0 < hours_to_ko < 3
                if should_refresh_odds(cls) or near_kickoff:
                    out.append({"fixture": fx, "row": row, "near_kickoff": near_kickoff})
    finally:
        conn.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduled odds refresh (1X2 only, no predictions)")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--max-fixtures", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = date.today()
    dates = [today, today + timedelta(days=1)]
    candidates = _discover_refresh_candidates(target_dates=dates, tz_name=args.timezone)[: args.max_fixtures]

    refreshed = 0
    skipped = 0
    errors: list[dict] = []
    settings = get_settings()

    for item in candidates:
        fx = item["fixture"]
        if args.dry_run:
            skipped += 1
            continue
        try:
            result = refresh_live_odds(fx, settings=settings)
            if result.get("success"):
                refreshed += 1
            else:
                errors.append({"fixture_id": fx.fixture_id, "status": result.get("status")})
        except Exception as exc:
            errors.append({"fixture_id": fx.fixture_id, "error": str(exc)[:200]})

    print(
        json.dumps(
            {
                "phase": PHASE,
                "dates": [d.isoformat() for d in dates],
                "candidates": len(candidates),
                "refreshed": refreshed,
                "skipped_dry_run": skipped,
                "errors": errors[:20],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
