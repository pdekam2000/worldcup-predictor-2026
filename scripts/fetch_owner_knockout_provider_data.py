#!/usr/bin/env python3
"""Fetch/update provider data for resolved owner knockout fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.knockout_provider import run_knockout_provider_fetch
from worldcup_predictor.owner_manual_exact.resolver import _date_tag, load_resolution_artifact, resolve_manual_match_list
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _parse_fixture_ids(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--fixture-ids", default=None, help="Comma-separated local fixture IDs")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-resolve", action="store_true")
    args = parser.parse_args()

    process_date = resolve_process_date(args.date, args.timezone)
    fixture_ids = _parse_fixture_ids(args.fixture_ids)

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

    result = run_knockout_provider_fetch(
        process_date=process_date,
        fixture_ids=fixture_ids,
        resolution=resolution,
        force=args.force,
    )

    fetch_path = Path("artifacts") / f"owner_knockout_provider_fetch_{_date_tag(process_date)}.json"
    print(
        json.dumps(
            {
                "counts": result.counts,
                "errors": result.errors,
                "artifact_path": str(fetch_path),
                "provider_map": str(
                    Path("artifacts") / f"owner_knockout_provider_fixture_map_{_date_tag(process_date)}.json"
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
