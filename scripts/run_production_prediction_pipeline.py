#!/usr/bin/env python3
"""IMPLEMENT-1 — Production prediction/evaluation pipeline entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.owner.production_pipeline.runner import (  # noqa: E402
    PipelineConfig,
    run_production_prediction_pipeline,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Production-safe prediction/evaluation pipeline")
    parser.add_argument(
        "--mode",
        choices=("daily", "hourly", "results-only", "predictions-only", "eval-only"),
        default="daily",
    )
    parser.add_argument("--date", default="today", help="today, tomorrow, or YYYY-MM-DD")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-lock", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--no-tomorrow", action="store_true")
    parser.add_argument("--no-shadow", action="store_true")
    parser.add_argument("--refresh-stale-odds", action="store_true")
    parser.add_argument("--max-odds-provider-calls", type=int, default=20)
    parser.add_argument("--strict-fresh-odds", action="store_true")
    parser.add_argument("--fixture-id", type=int, default=None)
    args = parser.parse_args()

    if args.mode == "hourly":
        mode = "hourly"
    else:
        mode = args.mode

    config = PipelineConfig(
        mode=mode,
        date_arg=args.date,
        timezone=args.timezone,
        dry_run=args.dry_run,
        limit=args.limit,
        include_tomorrow=not args.no_tomorrow,
        include_shadow_monitor=not args.no_shadow,
        skip_lock=args.skip_lock,
        refresh_stale_odds=args.refresh_stale_odds,
        max_odds_provider_calls=args.max_odds_provider_calls,
        strict_fresh_odds=args.strict_fresh_odds,
        fixture_id=args.fixture_id,
    )
    result = run_production_prediction_pipeline(config)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    if result.skipped_overlap:
        return 2
    if result.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
