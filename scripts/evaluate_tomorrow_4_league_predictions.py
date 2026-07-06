#!/usr/bin/env python3
"""Evaluate frozen tomorrow 4-league batch snapshots after results finalize."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import PHASE, TZ, evaluate_batch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{PHASE} — post-match evaluation")
    parser.add_argument("--date", default="tomorrow", help="tomorrow or YYYY-MM-DD (prediction date)")
    parser.add_argument("--timezone", default=TZ)
    args = parser.parse_args()

    result = evaluate_batch(date_arg=args.date, timezone=args.timezone)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
