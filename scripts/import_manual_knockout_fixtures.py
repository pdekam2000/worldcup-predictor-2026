#!/usr/bin/env python3
"""Import knockout WC fixtures for manual owner match list (safe upsert, no duplicates)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.fixture_import import import_knockout_fixtures, save_import_audit
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--from-date", default="2026-07-01")
    parser.add_argument("--to-date", default="2026-07-05")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    process_date = resolve_process_date(args.date)
    result = import_knockout_fixtures(
        from_date=args.from_date,
        to_date=args.to_date,
        dry_run=args.dry_run,
    )
    path = save_import_audit(result, process_date=process_date)
    print(
        json.dumps(
            {
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped_existing": result.skipped_existing,
                "api_fetched": result.api_fetched,
                "errors": result.errors,
                "artifact_path": str(path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
