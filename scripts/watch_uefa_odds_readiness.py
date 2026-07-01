#!/usr/bin/env python3
"""PHASE EURO-C3 Part A — UEFA odds watch + ECSE readiness monitor (owner/internal)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c3_odds_watch import (
    READINESS_PATH,
    SUMMARY_PATH,
    append_readiness_jsonl,
    build_watch_summary,
    final_recommendation,
    watch_uefa_odds_readiness,
)
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C3 UEFA odds readiness watch")
    parser.add_argument("--competitions", nargs="+", default=list(UEFA_CUP_KEYS))
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-api-football-calls", type=int, default=100)
    parser.add_argument("--max-sportmonks-calls", type=int, default=100)
    parser.add_argument("--max-oddalerts-calls", type=int, default=100)
    parser.add_argument("--cache-first", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--only-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true", help="Overwrite newer odds snapshots")
    parser.add_argument("--crosswalk", type=str, default="artifacts/euro_c2_sportmonks_crosswalk.json")
    parser.add_argument("--summary", type=str, default=str(SUMMARY_PATH))
    parser.add_argument("--readiness-jsonl", type=str, default=str(READINESS_PATH))
    args = parser.parse_args()

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    call_log = DailyProviderCallLog(
        run_date=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat(),
        quota=ProviderQuotaGuard(
            max_api_football=args.max_api_football_calls,
            max_sportmonks=args.max_sportmonks_calls,
            max_oddalerts=args.max_oddalerts_calls,
            no_provider_calls=args.dry_run,
        ),
    )

    result = watch_uefa_odds_readiness(
        repo,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
        dry_run=args.dry_run,
        max_api_football_calls=args.max_api_football_calls,
        max_sportmonks_calls=args.max_sportmonks_calls,
        max_oddalerts_calls=args.max_oddalerts_calls,
        cache_first=args.cache_first,
        only_missing=args.only_missing,
        force=args.force,
        crosswalk_path=Path(args.crosswalk),
        settings=settings,
        call_log=call_log,
    )

    recommendation = final_recommendation(result)
    summary = build_watch_summary(result, final_recommendation=recommendation)
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readiness_path = append_readiness_jsonl(result.fixture_rows, Path(args.readiness_jsonl))
    repo.close()

    print(f"EURO-C3 odds watch complete (dry_run={args.dry_run})")
    print(f"  fixtures_scanned: {result.fixtures_scanned}")
    print(f"  ready_full: {result.ready_full_before} -> {result.ready_full_after}")
    print(f"  ready_partial: {result.ready_partial_before} -> {result.ready_partial_after}")
    print(f"  newly_imported: {result.imported_count}")
    print(f"  provider_calls: {result.provider_calls}")
    print(f"  recommendation: {recommendation}")
    print(f"  summary: {summary_path}")
    print(f"  readiness: {readiness_path}")
    if result.log_path:
        print(f"  log: {result.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
