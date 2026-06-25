#!/usr/bin/env python3
"""Phase 59D — Populate production predictions for Elite Shadow fixture set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.admin.shadow_fixture_production_population import (
    load_shadow_fixture_ids,
    populate_missing_production_predictions,
    population_summary_dict,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Populate production predictions for shadow fixtures")
    parser.add_argument("--dry-run", action="store_true", help="Audit only; do not generate predictions")
    parser.add_argument("--fixture-id", type=int, action="append", dest="fixture_ids", help="Limit to fixture ID(s)")
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    args = parser.parse_args()

    fixture_ids, market_rows = load_shadow_fixture_ids()
    print(f"Shadow fixtures: {len(fixture_ids)} | market rows: {market_rows}")

    result = populate_missing_production_predictions(
        dry_run=args.dry_run,
        fixture_ids=args.fixture_ids,
    )
    summary = population_summary_dict(result)

    artifact = ROOT / "artifacts" / "phase59d_populate_shadow_fixture_production"
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / "population_result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Existing production: {summary['existing_count']}")
        print(f"Missing production: {summary['missing_count']}")
        if not args.dry_run:
            print(f"Generated: {summary['generated_count']}")
            print(f"Failed: {summary['failed_count']}")
            before = summary.get("comparison_before") or {}
            after = summary.get("comparison_after") or {}
            print(
                f"Comparable before/after: {before.get('total_comparable', 0)} -> {after.get('total_comparable', 0)}"
            )
            print(
                f"Missing production rows before/after: "
                f"{before.get('missing_production_count', 0)} -> {after.get('missing_production_count', 0)}"
            )
        if summary.get("failed"):
            for item in summary["failed"][:5]:
                print(f"  FAIL {item}")

    return 0 if not summary.get("failed_count") or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
