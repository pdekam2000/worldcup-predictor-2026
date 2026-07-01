#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-3 — Build owner daily control panel report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.control_panel import build_owner_daily_control_panel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build owner daily control panel report")
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    args = parser.parse_args()

    result = build_owner_daily_control_panel(date_arg=args.date, timezone=args.timezone)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
