#!/usr/bin/env python3
"""Phase 54F-4 — import Sportmonks xG from feature-store cache (0 API calls)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f4_xg_parser_and_backfill"
DEFAULT_CACHE = ROOT / "data" / "feature_store" / "sportmonks_xg" / "raw"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import xG from feature-store JSON cache")
    parser.add_argument("--cache-dir", type=str, default=str(DEFAULT_CACHE))
    parser.add_argument("--league-id", type=int, default=0, help="0 = all leagues")
    parser.add_argument("--force-reimport", action="store_true")
    parser.add_argument("--metric-key", action="append", default=["xg"])
    args = parser.parse_args()

    from worldcup_predictor.feature_store.sportmonks_xg_store import SportmonksXgFeatureStore

    metric_keys = frozenset(k.strip().lower() for k in args.metric_key if k.strip())
    require_team_xg = "xg" in metric_keys and len(metric_keys) == 1

    store = SportmonksXgFeatureStore()
    if not store.configured:
        out = {"error": "postgres_not_configured"}
        print(json.dumps(out, indent=2))
        return 1

    cache_dir = Path(args.cache_dir)
    n_files = len(list(cache_dir.glob("*.json"))) if cache_dir.is_dir() else 0
    if n_files == 0:
        out = {"error": "cache_dir_empty", "cache_dir": str(cache_dir)}
        print(json.dumps(out, indent=2))
        return 1

    result = store.backfill_from_cache_dir(
        cache_dir,
        job_key="phase54f4_cache_import",
        league_id=args.league_id if args.league_id > 0 else None,
        force_reimport=args.force_reimport,
        metric_keys=metric_keys if not require_team_xg else None,
        require_team_xg=require_team_xg,
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "phase": "54F-4",
        "cache_dir": str(cache_dir),
        "cache_files": n_files,
        "league_id_filter": args.league_id if args.league_id > 0 else None,
        "fixtures_processed": result.fixtures_processed,
        "fixtures_imported": result.fixtures_imported,
        "fixtures_empty": result.fixtures_empty,
        "fixtures_skipped": result.fixtures_skipped,
        "fixtures_error": result.fixtures_error,
        "records_written": result.records_written,
        "api_calls_cached": result.api_calls_cached,
        "errors": result.errors[:20],
    }
    (ARTIFACT_DIR / "cache_import.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if result.fixtures_imported > 0 or result.records_written > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
