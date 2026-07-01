#!/usr/bin/env python3
"""PHASE DAILY-OWNER-2 — Import missing daily odds (owner/internal)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS
from worldcup_predictor.owner_daily.odds_import import import_daily_odds

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import daily odds for owner fixtures")
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--competitions", nargs="+", default=list(DAILY_SUPPORTED_COMPETITIONS))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-api-football-calls", type=int, default=100)
    parser.add_argument("--max-oddalerts-calls", type=int, default=100)
    parser.add_argument("--max-sportmonks-calls", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-missing", action="store_true", default=True)
    parser.add_argument("--no-only-missing", action="store_false", dest="only_missing")
    parser.add_argument("--force", action="store_true", help="Overwrite newer odds snapshots")
    parser.add_argument("--no-provider-calls", action="store_true")
    args = parser.parse_args()

    result = import_daily_odds(
        date_arg=args.date,
        timezone=args.timezone,
        competition_keys=args.competitions,
        limit=args.limit,
        dry_run=args.dry_run,
        only_missing=args.only_missing,
        force=args.force,
        max_api_football_calls=args.max_api_football_calls,
        max_oddalerts_calls=args.max_oddalerts_calls,
        max_sportmonks_calls=args.max_sportmonks_calls,
        no_provider_calls=args.no_provider_calls,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
