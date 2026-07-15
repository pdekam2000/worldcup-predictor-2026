#!/usr/bin/env python3
"""Run canonical daily prediction → freeze → evaluation → reporting pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner_daily.pipeline.orchestrator import DailyPipelineConfig, run_daily_pipeline

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily prediction/freeze/evaluation/reporting pipeline")
    parser.add_argument("--date", default="today", help="today, tomorrow, or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-provider-calls", action="store_true")
    parser.add_argument("--skip-result-sync", action="store_true")
    parser.add_argument("--force-predictions", action="store_true")
    parser.add_argument("--refresh-stale-odds", action="store_true")
    parser.add_argument("--strict-fresh-odds", action="store_true")
    parser.add_argument("--fixture-id", type=int, default=None)
    args = parser.parse_args()

    cfg = DailyPipelineConfig(
        date_arg=args.date,
        timezone=args.timezone,
        limit=args.limit,
        dry_run=args.dry_run,
        no_provider_calls=args.no_provider_calls,
        skip_result_sync=args.skip_result_sync,
        force_predictions=args.force_predictions,
        refresh_stale_odds=args.refresh_stale_odds,
        strict_fresh_odds=args.strict_fresh_odds,
        fixture_id=args.fixture_id,
        discovery_scope="owner",
        emit_evaluation_report=not args.skip_result_sync,
    )
    result = run_daily_pipeline(cfg)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if result.pipeline_status.endswith("NO_FIXTURES"):
        return 0
    if result.pipeline_status == "DAILY_PIPELINE_BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
