#!/usr/bin/env python3
"""HOTFIX WC-RESULT-SYNC-2 — automatic ECSE snapshot result sync + evaluation backfill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_live.result_sync import (
    SUMMARY_PATH,
    SYNC_LOG_PATH,
    backfill_penalty_metadata_for_fixtures,
    build_ecse_wc_evaluation_summary,
    scan_ecse_snapshot_result_candidates,
    sync_ecse_snapshot_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync provider results for ECSE snapshot fixtures past kickoff.",
    )
    parser.add_argument(
        "--competition",
        default="world_cup_2026",
        help="ECSE competition key (default: world_cup_2026)",
    )
    parser.add_argument(
        "--fixture-ids",
        nargs="*",
        type=int,
        default=None,
        help="Optional explicit API-Football fixture IDs",
    )
    parser.add_argument(
        "--past-only",
        action="store_true",
        default=True,
        help="Only fixtures whose kickoff is in the past (default: true)",
    )
    parser.add_argument(
        "--include-future",
        action="store_true",
        help="Include future kickoffs (overrides --past-only)",
    )
    parser.add_argument(
        "--min-hours-since-kickoff",
        type=float,
        default=2.0,
        help="Safety window: only sync if kickoff older than N hours (default: 2)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite valid finished results")
    parser.add_argument("--no-ecse-backfill", action="store_true")
    parser.add_argument("--scan-only", action="store_true", help="List candidates without syncing")
    parser.add_argument(
        "--backfill-penalty-only",
        action="store_true",
        help="Only backfill match_outcome_type/penalty_score; do not change ECSE scores/evaluations",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    past_only = not args.include_future

    try:
        if args.backfill_penalty_only:
            if not args.fixture_ids:
                print("Error: --backfill-penalty-only requires --fixture-ids", file=sys.stderr)
                return 2
            payload = {
                "backfill": backfill_penalty_metadata_for_fixtures(
                    settings=settings,
                    fixture_ids=args.fixture_ids,
                    competition_key=args.competition,
                    dry_run=args.dry_run,
                )
            }
            print(json.dumps(payload, indent=2, default=str))
            return 0 if payload["backfill"].get("errors", 0) == 0 else 1

        if args.scan_only:
            candidates = scan_ecse_snapshot_result_candidates(
                conn,
                competition_key=args.competition,
                past_only=past_only,
                min_hours_since_kickoff=args.min_hours_since_kickoff,
                fixture_ids=args.fixture_ids,
                settings=settings,
            )
            payload = {
                "competition_key": args.competition,
                "candidate_count": len(candidates),
                "candidates": [c.to_dict() for c in candidates],
            }
            print(json.dumps(payload, indent=2, default=str))
            return 0

        outcome = sync_ecse_snapshot_results(
            settings=settings,
            competition_key=args.competition,
            fixture_ids=args.fixture_ids,
            past_only=past_only,
            min_hours_since_kickoff=args.min_hours_since_kickoff,
            dry_run=args.dry_run,
            force=args.force,
            run_ecse_backfill=not args.no_ecse_backfill,
            limit=args.limit,
        )
        summary = build_ecse_wc_evaluation_summary(conn, competition_key=args.competition)
        payload = {
            "sync": outcome.to_dict(),
            "evaluation_summary": summary,
        }
    finally:
        conn.close()

    if args.json_out:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(payload, indent=2, default=str))

    artifacts_dir = ROOT / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    latest = artifacts_dir / "ecse_snapshot_result_sync_latest.json"
    latest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {latest}")
    print(f"Log: {SYNC_LOG_PATH}")
    print(f"Summary: {SUMMARY_PATH}")

    return 0 if outcome.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
