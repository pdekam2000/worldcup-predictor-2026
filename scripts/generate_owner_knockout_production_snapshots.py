#!/usr/bin/env python3
"""Generate owner-only WDE/ECSE production snapshots for resolved knockout fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.knockout_production import (
    generate_knockout_production_snapshots,
    write_knockout_production_artifacts,
)
from worldcup_predictor.owner_manual_exact.resolver import load_resolution_artifact
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _parse_fixture_ids(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Owner-only WDE/ECSE production snapshot generation for knockout fixtures"
    )
    parser.add_argument("--date", default="today", help="today or YYYY-MM-DD")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--fixture-ids", default="", help="Optional comma-separated fixture IDs")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing WDE/ECSE production rows",
    )
    args = parser.parse_args()

    process_date = resolve_process_date(args.date, args.timezone)
    fixture_ids = _parse_fixture_ids(args.fixture_ids)
    resolution = load_resolution_artifact(process_date)
    if resolution is None:
        print(json.dumps({"error": "missing resolution artifact — run resolve_manual_owner_match_list first"}, indent=2))
        return 1

    result = generate_knockout_production_snapshots(
        process_date=process_date,
        fixture_ids=fixture_ids,
        force=args.force,
        resolution=resolution,
    )
    paths = write_knockout_production_artifacts(result, process_date=process_date)

    summary = {
        "selected": result.selected,
        "wde_generated": result.wde_generated,
        "ecse_generated": result.ecse_generated,
        "skipped_existing_wde": result.skipped_existing_wde,
        "skipped_existing_ecse": result.skipped_existing_ecse,
        "wde_skip_reasons": result.wde_skip_reasons,
        "ecse_skip_reasons": result.ecse_skip_reasons,
        **paths,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
