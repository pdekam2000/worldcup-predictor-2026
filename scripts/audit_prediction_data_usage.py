#!/usr/bin/env python3
"""PHASE OWNER-DAILY-PREDICT-EVAL-1 Part D — Audit prediction data / training usage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.data_audit import audit_prediction_data_usage
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date
from worldcup_predictor.owner_predict_eval.fixture_discovery import load_today_fixtures_artifact

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prediction data usage audit")
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    args = parser.parse_args()

    target = resolve_process_date(args.date, args.timezone)
    fx = load_today_fixtures_artifact(target)
    fixture_ids = [int(f["fixture_id"]) for f in (fx or {}).get("fixtures") or []]

    result = audit_prediction_data_usage(
        date_arg=args.date,
        timezone=args.timezone,
        fixture_ids=fixture_ids or None,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
