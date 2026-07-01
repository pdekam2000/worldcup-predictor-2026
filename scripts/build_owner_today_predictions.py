#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-1 Part B — Build owner today predictions report (load only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.dates import resolve_process_date
from worldcup_predictor.owner_predict_eval.fixture_discovery import discover_today_fixtures, load_today_fixtures_artifact
from worldcup_predictor.owner_predict_eval.predictions import build_today_predictions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner today predictions builder")
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--refresh-fixtures", action="store_true")
    args = parser.parse_args()

    if args.refresh_fixtures:
        fixtures_payload = discover_today_fixtures(
            date_arg=args.date,
            timezone=args.timezone,
            limit=args.limit,
        ).to_dict()
    else:
        target = resolve_process_date(args.date, args.timezone)
        fixtures_payload = load_today_fixtures_artifact(target)
        if not fixtures_payload:
            fixtures_payload = discover_today_fixtures(
                date_arg=args.date,
                timezone=args.timezone,
                limit=args.limit,
            ).to_dict()

    result = build_today_predictions(fixtures_payload)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
