#!/usr/bin/env python3
"""PHASE EURO-C2 Part C/D — Import Sportmonks UEFA odds (canonical API fixture IDs)."""

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
from worldcup_predictor.owner.euro_c2_sportmonks_odds import (
    build_ecse_readiness_artifact,
    build_uefa_sportmonks_crosswalk,
    final_recommendation,
    import_sportmonks_uefa_odds,
    scan_crosswalk_odds_availability,
)

CROSSWALK_PATH = ROOT / "artifacts" / "euro_c2_sportmonks_crosswalk.json"
SCAN_PATH = ROOT / "artifacts" / "euro_c2_sportmonks_odds_availability.json"
READINESS_PATH = ROOT / "artifacts" / "euro_c2_ecse_readiness_after_sportmonks.json"
SUMMARY_PATH = ROOT / "artifacts" / "euro_c2_sportmonks_odds_import_summary.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C2 Sportmonks UEFA odds import")
    parser.add_argument("--competitions", nargs="+", default=list(UEFA_CUP_KEYS))
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-api-calls", type=int, default=100)
    parser.add_argument("--cache-first", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--only-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--crosswalk", type=str, default=str(CROSSWALK_PATH))
    args = parser.parse_args()

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = repo._conn

    crosswalk_path = Path(args.crosswalk)
    if crosswalk_path.exists():
        crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    else:
        crosswalk = build_uefa_sportmonks_crosswalk(
            conn, competition_keys=list(args.competitions), days_ahead=args.days_ahead
        )
        crosswalk_path.parent.mkdir(parents=True, exist_ok=True)
        crosswalk_path.write_text(json.dumps(crosswalk, ensure_ascii=False, indent=2), encoding="utf-8")

    scan = scan_crosswalk_odds_availability(
        conn,
        crosswalk,
        settings=settings,
        max_api_calls=0,
        cache_first=args.cache_first,
        dry_run=False,
    )
    SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCAN_PATH.write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")

    import_result, readiness_rows = import_sportmonks_uefa_odds(
        repo,
        crosswalk,
        settings=settings,
        dry_run=args.dry_run,
        max_api_calls=args.max_api_calls,
        cache_first=args.cache_first,
        only_missing=args.only_missing,
        force=args.force,
    )
    repo.close()

    readiness = build_ecse_readiness_artifact(readiness_rows)
    READINESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    READINESS_PATH.write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")

    recommendation = final_recommendation(crosswalk, scan, import_result, dry_run=args.dry_run)
    summary = {
        "phase": "EURO-C2",
        "generated_at_utc": readiness["generated_at_utc"],
        "crosswalk_accepted": crosswalk.get("accepted_count"),
        "crosswalk_ambiguous": crosswalk.get("ambiguous_count"),
        "crosswalk_no_match": crosswalk.get("no_match_count"),
        "imported_odds_count": import_result.imported_count,
        "ecse_ready_count": import_result.ecse_ready_count,
        "api_calls_used": import_result.api_calls_used,
        "cache_hits": import_result.cache_hits,
        "dry_run": args.dry_run,
        "fixtures_with_odds_scan": scan.get("fixtures_with_odds"),
        "skipped_count": len(import_result.skipped),
        "provider_errors_count": len(import_result.provider_errors),
        "log_path": import_result.log_path,
        "final_recommendation": recommendation,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"EURO-C2 import {'(dry-run) ' if args.dry_run else ''}complete")
    print(f"Crosswalk accepted: {crosswalk.get('accepted_count')}")
    print(f"Imported: {import_result.imported_count}")
    print(f"ECSE-ready: {import_result.ecse_ready_count}")
    print(f"API calls: {import_result.api_calls_used}")
    print(f"Recommendation: {recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
