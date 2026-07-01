#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-3 Part E — Run full owner daily prediction + eval cycle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.runner import run_owner_daily_prediction_and_eval

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Owner daily prediction and evaluation runner")
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    result = run_owner_daily_prediction_and_eval(
        date_arg=args.date,
        timezone=args.timezone,
        limit=args.limit,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
