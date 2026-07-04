#!/usr/bin/env python3
"""FIXTURE-SYNC-1 Part C — Sync upcoming WC fixtures + optional stale-NS repair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import os

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner_daily.wc_schedule_sync import (
    PHASE,
    _parse_date_arg,
    repair_stale_ns_wc_fixtures,
    resolve_competition_key,
    sync_wc_upcoming_fixtures,
)

OUTPUT_JSON = ROOT / "artifacts" / "fixture_sync" / "fixture_sync_1_sync_latest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="FIXTURE-SYNC-1 WC upcoming fixture sync")
    parser.add_argument("--competition", default="wc")
    parser.add_argument("--from-date", default="today")
    parser.add_argument("--to-date", default=None)
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--source", default="auto", choices=("auto", "api_football", "sportmonks"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true", help="Persist changes (disables dry-run)")
    parser.add_argument("--max-provider-calls", type=int, default=20)
    parser.add_argument("--repair-stale-ns", action="store_true", help="Repair past-kickoff NS fixtures from provider")
    args = parser.parse_args()

    settings = get_settings()
    comp = resolve_competition_key(args.competition)
    from_d = _parse_date_arg(args.from_date, args.timezone)
    to_d = _parse_date_arg(args.to_date, args.timezone) if args.to_date else None
    dry_run = args.dry_run or not args.write

    payload: dict = {"phase": PHASE, "competition": comp, "dry_run": dry_run}

    if args.repair_stale_ns:
        repair = repair_stale_ns_wc_fixtures(
            settings=settings,
            competition_key=comp,
            max_provider_calls=args.max_provider_calls,
            dry_run=dry_run,
        )
        payload["stale_ns_repair"] = repair.to_dict()

    sync = sync_wc_upcoming_fixtures(
        from_date=from_d,
        to_date=to_d,
        source=args.source,
        competition_key=comp,
        max_provider_calls=args.max_provider_calls,
        dry_run=dry_run,
        settings=settings,
    )
    payload["upcoming_sync"] = sync.to_dict()

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
