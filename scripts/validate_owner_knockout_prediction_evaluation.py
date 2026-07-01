#!/usr/bin/env python3
"""Validate owner knockout prediction evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.knockout_evaluation_validation import (
    validate_owner_knockout_prediction_evaluation,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate owner knockout prediction evaluation")
    parser.add_argument("--date", default="today", help="today, yesterday, or YYYY-MM-DD")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    result = validate_owner_knockout_prediction_evaluation(
        date_arg=args.date,
        timezone=args.timezone,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
