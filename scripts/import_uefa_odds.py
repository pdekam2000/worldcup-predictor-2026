#!/usr/bin/env python3
"""PHASE EURO-C Part B — Import UEFA odds (owner/internal, no ECSE generation)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_c_odds_import import (
    build_import_summary,
    import_uefa_odds,
    scan_uefa_odds_availability,
)

SCAN_PATH = ROOT / "artifacts" / "euro_c_odds_availability_scan.json"
SUMMARY_PATH = ROOT / "artifacts" / "euro_c_odds_import_summary.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C UEFA odds import")
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=list(UEFA_CUP_KEYS),
    )
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-api-calls", type=int, default=100)
    parser.add_argument("--cache-first", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--only-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true", help="Import even when newer snapshot exists")
    parser.add_argument("--scan-output", type=str, default=str(SCAN_PATH))
    parser.add_argument("--summary", type=str, default=str(SUMMARY_PATH))
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    scan = scan_uefa_odds_availability(
        conn,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
    )
    scan_path = Path(args.scan_output)
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    import_result = import_uefa_odds(
        repo,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
        dry_run=args.dry_run,
        max_api_calls=args.max_api_calls,
        cache_first=args.cache_first,
        only_missing=args.only_missing,
        force=args.force,
        settings=settings,
    )

    post_scan = scan_uefa_odds_availability(
        conn,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
    )
    conn.close()
    repo.close()

    summary = build_import_summary(post_scan, import_result)
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"EURO-C import {'(dry-run) ' if args.dry_run else ''}complete")
    print(f"Fixtures scanned: {import_result.fixtures_scanned}")
    print(f"Imported: {import_result.imported_count}")
    print(f"API calls: {import_result.api_calls_used}")
    print(f"ECSE-ready: {import_result.ecse_ready_count}")
    print(f"Recommendation: {summary['final_recommendation']}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
