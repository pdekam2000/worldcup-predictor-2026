#!/usr/bin/env python3
"""Run domestic league control prediction batch."""

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
    discover_domestic_control_fixtures,
    run_domestic_control_batch,
    scan_domestic_dates,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD or omit for nearest eligible")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else None

    if args.scan_only:
        rows = scan_domestic_dates()
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if args.discover_only:
        result = discover_domestic_control_fixtures(target_date=target)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("status") == "discovered" else 1

    result = run_domestic_control_batch(target_date=target, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "batch_id": result.get("batch_id"),
                "target_date": result.get("target_date"),
                "payload_path": result.get("payload_path"),
                "selected": [
                    {
                        "fixture_id": m["fixture"]["fixture_id"],
                        "match": f"{m['fixture']['home_team']} vs {m['fixture']['away_team']}",
                        "league": m["fixture"]["competition_name"],
                    }
                    for m in result.get("matches") or []
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if result.get("status") == "DOMESTIC_LEAGUE_CONTROL_BATCH_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
