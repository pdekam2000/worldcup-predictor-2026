#!/usr/bin/env python3
"""PHASE ECSE-ODDALERTS-6 — Daily owner pipeline orchestrator."""

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
    REPORT_PATH,
    run_daily_oddalerts_ecse_owner_pipeline,
    state_artifact_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily OddAlerts → ECSE owner shadow monitor pipeline")
    parser.add_argument("--date", default="2026-07-01", help="Pipeline date YYYY-MM-DD or 'today'")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--download-gmail", action="store_true")
    parser.add_argument("--import-csv", action="store_true")
    parser.add_argument("--promote-odds-safe", action="store_true")
    parser.add_argument("--run-monitor", action="store_true")
    parser.add_argument("--only-eligible-v2", action="store_true", default=False)
    parser.add_argument("--tag", default="daily-owner-oddalerts")
    parser.add_argument("--write-odds", action="store_true", help="Execute safe odds promotion write (default: preview only)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    config = DailyPipelineConfig(
        process_date=args.date,
        window_days=args.window_days,
        download_gmail=args.download_gmail,
        import_csv=args.import_csv,
        promote_odds_safe=args.promote_odds_safe,
        run_monitor=args.run_monitor,
        only_eligible_v2=args.only_eligible_v2,
        pipeline_tag=args.tag,
        dry_run_promotion=not args.write_odds,
        verbose=args.verbose,
    )

    result = run_daily_oddalerts_ecse_owner_pipeline(config)

    out = result.to_state_dict()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"State: {state_artifact_path(result.process_date)}")
    print(f"Recommendation: {result.final_recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
