#!/usr/bin/env python3
"""Owner-only post-match evaluation for knockout WDE/ECSE/manual predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.knockout_evaluation import evaluate_owner_knockout_predictions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate owner knockout predictions (owner-only)")
    parser.add_argument("--date", default="today", help="today, yesterday, or YYYY-MM-DD")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument(
        "--no-api-refresh",
        action="store_true",
        help="Do not refresh missing results from API-Football",
    )
    args = parser.parse_args()

    result = evaluate_owner_knockout_predictions(
        date_arg=args.date,
        timezone=args.timezone,
        refresh_api=not args.no_api_refresh,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
