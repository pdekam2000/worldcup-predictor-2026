#!/usr/bin/env python3
"""Audit ECSE data availability for resolved owner knockout fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.knockout_provider import (
    run_knockout_ecse_data_audit,
    write_knockout_ecse_audit_artifacts,
)
from worldcup_predictor.owner_manual_exact.resolver import load_resolution_artifact, resolve_manual_match_list
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--skip-resolve", action="store_true")
    args = parser.parse_args()

    process_date = resolve_process_date(args.date, args.timezone)
    resolution = None
    if not args.skip_resolve:
        resolution = resolve_manual_match_list(
            process_date=process_date, timezone=args.timezone, auto_import=True
        )
    if resolution is None:
        resolution = load_resolution_artifact(process_date)
    if resolution is None:
        print(json.dumps({"error": "no resolution artifact"}, indent=2))
        return 1

    result = run_knockout_ecse_data_audit(process_date=process_date, resolution=resolution)
    paths = write_knockout_ecse_audit_artifacts(result, process_date=process_date)

    print(
        json.dumps(
            {
                "fixture_count": result.fixture_count,
                "summary": result.summary,
                **paths,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
