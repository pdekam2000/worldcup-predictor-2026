#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-1 Part A — Find today's fixtures with data availability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.fixture_discovery import discover_today_fixtures

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner today fixture discovery")
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--fetch-if-missing", action="store_true")
    args = parser.parse_args()

    result = discover_today_fixtures(
        date_arg=args.date,
        timezone=args.timezone,
        limit=args.limit,
        fetch_if_missing=args.fetch_if_missing,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
