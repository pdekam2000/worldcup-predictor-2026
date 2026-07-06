#!/usr/bin/env python3
"""Evaluate domestic control batch and compare with UEFA reference batch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.domestic_league_control import (
    PHASE,
    evaluate_experiment_comparison,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{PHASE} — evaluation + A/B comparison")
    parser.add_argument("--date", default=None, help="domestic batch date YYYY-MM-DD")
    args = parser.parse_args()
    target = date.fromisoformat(args.date) if args.date else None
    result = evaluate_experiment_comparison(domestic_date=target)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
