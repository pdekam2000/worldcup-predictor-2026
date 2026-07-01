#!/usr/bin/env python3
"""PHASE EURO-C4 Part D — Import OddAlerts odds for UEFA fixtures."""

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
from worldcup_predictor.owner.euro_c4_oddalerts import (
    compute_ecse_readiness_after_oddalerts,
    import_oddalerts_uefa_odds,
)

DEFAULT_READINESS = ROOT / "artifacts" / "euro_c4_ecse_readiness_after_oddalerts.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="EURO-C4 OddAlerts odds import")
    parser.add_argument("--competitions", nargs="+", default=list(UEFA_CUP_KEYS))
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--max-api-calls", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-cache-first", action="store_true")
    parser.add_argument("--readiness", action="store_true", help="Compute ECSE readiness after import")
    args = parser.parse_args()

    repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
    result = import_oddalerts_uefa_odds(
        repo,
        competition_keys=list(args.competitions),
        days_ahead=args.days_ahead,
        dry_run=args.dry_run,
        max_api_calls=args.max_api_calls,
        force=args.force,
        cache_first=not args.no_cache_first,
    )

    readiness = None
    if args.readiness:
        readiness = compute_ecse_readiness_after_oddalerts(repo._conn)

    repo.close()

    print(f"Fixtures scanned: {result.fixtures_scanned}")
    print(f"Imported: {result.imported_count} | Skipped: {result.skipped}")
    print(f"Provider calls: {result.provider_calls}")
    if readiness:
        print(f"Readiness status counts: {readiness.get('status_counts')}")
        print(f"Written readiness: {DEFAULT_READINESS}")

    summary = result.to_dict()
    if readiness:
        summary["readiness_status_counts"] = readiness.get("status_counts")
    out = ROOT / "artifacts" / "euro_c4_oddalerts_import_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
