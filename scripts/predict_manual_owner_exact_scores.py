#!/usr/bin/env python3
"""Part B — Owner manual exact final score predictions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.predictor import predict_manual_exact_scores
from worldcup_predictor.owner_manual_exact.resolver import load_resolution_artifact, resolve_manual_match_list
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--skip-resolve", action="store_true", help="Use existing resolution artifact only")
    args = parser.parse_args()

    process_date = resolve_process_date(args.date, args.timezone)
    resolution = None
    if args.skip_resolve:
        resolution = load_resolution_artifact(process_date)
    if resolution is None:
        resolution = resolve_manual_match_list(
            process_date=process_date, timezone=args.timezone, auto_import=True
        )

    result = predict_manual_exact_scores(
        date_arg=args.date,
        timezone=args.timezone,
        resolution=resolution,
    )
    print(
        json.dumps(
            {
                "match_count": result["match_count"],
                "resolved_count": result["resolved_count"],
                "json_path": result.get("json_path"),
                "md_path": result.get("md_path"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
