#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-3 Part C — Evaluate yesterday's owner predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.yesterday_eval import evaluate_yesterday_predictions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner yesterday prediction evaluation")
    parser.add_argument("--date", default="yesterday", help="yesterday, today, or YYYY-MM-DD (evaluates that date)")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument(
        "--refresh-missing-results",
        action="store_true",
        help="Re-check only fixtures waiting for results; preserve already evaluated rows",
    )
    args = parser.parse_args()

    result = evaluate_yesterday_predictions(
        date_arg=args.date,
        timezone=args.timezone,
        refresh_missing_results=args.refresh_missing_results,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
