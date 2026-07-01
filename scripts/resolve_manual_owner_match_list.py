#!/usr/bin/env python3
"""Part A — Resolve manual owner match list to internal fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_manual_exact.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_manual_exact.resolver import resolve_manual_match_list
from worldcup_predictor.owner_predict_eval.dates import resolve_process_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--no-import", action="store_true", help="Skip auto-import from API-Football")
    args = parser.parse_args()

    process_date = resolve_process_date(args.date, args.timezone)
    result = resolve_manual_match_list(
        process_date=process_date,
        timezone=args.timezone,
        auto_import=not args.no_import,
    )
    print(
        json.dumps(
            {
                "match_count": result["match_count"],
                "resolved_count": result["resolved_count"],
                "manual_only_count": result["manual_only_count"],
                "import_audit": {
                    k: result.get("import_audit", {}).get(k)
                    for k in ("inserted", "updated", "skipped_existing", "api_fetched")
                }
                if result.get("import_audit")
                else None,
                "artifact_path": result.get("artifact_path"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
