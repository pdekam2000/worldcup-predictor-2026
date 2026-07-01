#!/usr/bin/env python3
"""Scheduler-safe single run of daily OddAlerts ECSE owner pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner.daily_oddalerts_ecse_pipeline import (  # noqa: E402
    DailyPipelineConfig,
    run_daily_oddalerts_ecse_owner_pipeline,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run daily OddAlerts ECSE owner pipeline once (cron/systemd safe)"
    )
    parser.add_argument("--date", default="today")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--write-odds", action="store_true", help="Allow safe odds snapshot writes")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = DailyPipelineConfig(
        process_date=args.date,
        window_days=args.window_days,
        download_gmail=True,
        import_csv=True,
        promote_odds_safe=True,
        run_monitor=True,
        only_eligible_v2=True,
        pipeline_tag="daily-owner-oddalerts",
        dry_run_promotion=not args.write_odds,
        verbose=args.verbose,
    )

    try:
        result = run_daily_oddalerts_ecse_owner_pipeline(config)
    except Exception as exc:
        print(json.dumps({"error": str(exc), "status": "failed"}, indent=2), file=sys.stderr)
        return 1

    rec = result.final_recommendation
    print(json.dumps({"final_recommendation": rec, "run_id": result.run_id}, indent=2))

    if rec == "DO_NOT_RUN_DAILY_PIPELINE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
