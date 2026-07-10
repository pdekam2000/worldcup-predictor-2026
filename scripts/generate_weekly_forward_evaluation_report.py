#!/usr/bin/env python3
"""Generate weekly forward evaluation report (read-only)."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.weekly_report import generate_weekly_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--end-date", default=None)
    args = parser.parse_args()
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    path = generate_weekly_report(end_date=end, days=args.days)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
