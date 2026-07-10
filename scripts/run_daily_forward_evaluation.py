#!/usr/bin/env python3
"""Run daily forward evaluation batch (discovery → gate → freeze → evaluate)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.runner import run_daily_forward_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily forward evaluation batch")
    parser.add_argument("--date", default=None, help="Evaluation date YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_daily_forward_evaluation(
        target_date=args.date,
        timezone=args.timezone,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
