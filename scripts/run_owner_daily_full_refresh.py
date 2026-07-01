#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-4 — Run full owner daily refresh pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.full_refresh import run_owner_daily_full_refresh

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner daily full refresh (predict, eval, panel, validate)")
    parser.add_argument(
        "--date",
        default="today",
        help="today, now, yesterday, tomorrow, or YYYY-MM-DD",
    )
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation step")
    parser.add_argument(
        "--no-refresh-missing-results",
        action="store_true",
        help="Skip yesterday missing-results refresh (default: refresh enabled)",
    )
    args = parser.parse_args()

    result = run_owner_daily_full_refresh(
        date_arg=args.date,
        timezone=args.timezone,
        skip_validation=args.skip_validation,
        refresh_missing_results=not args.no_refresh_missing_results,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if result.validation_passed is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
