#!/usr/bin/env python3
"""Run tomorrow 4-league production prediction batch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import (
    PHASE,
    TZ,
    discover_and_select_fixtures,
    run_batch_predictions,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=PHASE)
    parser.add_argument("--date", default="tomorrow", help="tomorrow or YYYY-MM-DD")
    parser.add_argument("--timezone", default=TZ)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()

    if args.discover_only:
        result = discover_and_select_fixtures(date_arg=args.date, timezone=args.timezone)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("preselected_count", result.get("selected_count", 0)) >= 4 else 1

    result = run_batch_predictions(
        date_arg=args.date,
        timezone=args.timezone,
        dry_run=args.dry_run,
    )
    print(json.dumps(
        {
            "status": result.get("status"),
            "batch_id": result.get("batch_id"),
            "target_date": result.get("target_date"),
            "payload_path": result.get("payload_path"),
            "prediction_report_path": result.get("prediction_report_path"),
            "selected": [
                {
                    "fixture_id": m["fixture"]["fixture_id"],
                    "match": f"{m['fixture']['home_team']} vs {m['fixture']['away_team']}",
                    "competition": m["fixture"]["competition_name"],
                }
                for m in result.get("matches") or []
            ],
        },
        indent=2,
        ensure_ascii=False,
    ))
    return 0 if result.get("status") == "TOMORROW_4_LEAGUE_PRODUCTION_PREDICTIONS_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
