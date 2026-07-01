#!/usr/bin/env python3
"""PHASE DAILY-OWNER-1/2 — Safe scheduler entry for the full owner daily cycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_daily.cycle import DailyCycleConfig, run_daily_owner_cycle

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEDULER_DOC = """
# Owner daily prediction cycle — scheduling examples (NOT installed automatically)

## Daily morning run (08:00 Europe/Vienna) — with odds import
0 8 * * * cd /path/to/Footbal && python scripts/run_daily_owner_prediction_cycle.py --timezone Europe/Vienna --fetch-missing-odds --max-api-football-calls 100 --max-oddalerts-calls 100 --max-sportmonks-calls 100 >> logs/daily_owner_cycle.log 2>&1

## Pre-kickoff refresh (every 2 hours on match days)
0 */2 * * * cd /path/to/Footbal && python scripts/run_daily_owner_prediction_cycle.py --timezone Europe/Vienna --fetch-missing-odds --force-refresh >> logs/daily_owner_prematch.log 2>&1

## Post-match result sync (late evening)
0 23 * * * cd /path/to/Footbal && python scripts/run_daily_owner_prediction_cycle.py --timezone Europe/Vienna --force-refresh >> logs/daily_owner_results.log 2>&1
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run full owner daily prediction cycle",
        epilog="See --show-schedule-examples for cron/systemd samples.",
    )
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--date", default="today")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--fetch-missing-odds", action="store_true")
    parser.add_argument("--include-shadow", action="store_true")
    parser.add_argument("--max-api-football-calls", type=int, default=100)
    parser.add_argument("--max-oddalerts-calls", type=int, default=100)
    parser.add_argument("--max-sportmonks-calls", type=int, default=100)
    parser.add_argument("--no-provider-calls", action="store_true")
    parser.add_argument("--show-schedule-examples", action="store_true")
    args = parser.parse_args()

    if args.show_schedule_examples:
        print(SCHEDULER_DOC.strip())
        return 0

    config = DailyCycleConfig(
        date_arg=args.date,
        timezone=args.timezone,
        limit=args.limit,
        dry_run=args.dry_run,
        force_refresh=args.force_refresh,
        fetch_missing_odds=args.fetch_missing_odds,
        include_shadow=args.include_shadow,
        max_api_football_calls=args.max_api_football_calls,
        max_oddalerts_calls=args.max_oddalerts_calls,
        max_sportmonks_calls=args.max_sportmonks_calls,
        no_provider_calls=args.no_provider_calls,
    )
    result = run_daily_owner_cycle(config)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
