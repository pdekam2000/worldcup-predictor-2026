#!/usr/bin/env python3
"""Phase 54H — Sportmonks Pressure feature store backfill (cache-first, resumable)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "artifacts" / "phase54h_pressure_feature_store"
BATCH1_ARTIFACT = ROOT / "artifacts" / "phase54h4_pressure_backfill_batch1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sportmonks Pressure feature store backfill")
    parser.add_argument("--league-id", type=int, default=2, help="0 = all leagues in cache scan")
    parser.add_argument("--season-id", type=int, default=None)
    parser.add_argument("--fixture-id", type=int, default=None, help="Single fixture ingest (counts toward max-calls)")
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--max-pages", type=int, default=15)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--cache-dir", type=str, default="")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache-first reads for API backfill")
    parser.add_argument("--cache-first", action="store_true", default=True, help="Use cache before API (default)")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--force-reimport", action="store_true")
    parser.add_argument("--include-upcoming", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--job-key", type=str, default="", help="Manifest job key for resume")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip manifest-imported fixtures")
    parser.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    parser.add_argument("--save-raw", action="store_true", default=True, help="Save API payload to pressure raw cache")
    parser.add_argument("--resume", action="store_true", help="Alias: skip-existing + existing job-key")
    parser.add_argument("--plan-only", action="store_true", help="Print target estimate only; no ingest")
    parser.add_argument("--manifest", type=str, default="", help="JSON manifest of fixture IDs to backfill")
    parser.add_argument("--artifact-dir", type=str, default="", help="Batch artifact output directory")
    args = parser.parse_args()

    if args.resume and not args.job_key:
        args.job_key = f"phase54h_l{args.league_id}_resume"

    from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

    store = SportmonksPressureFeatureStore()
    out_root = Path(args.artifact_dir) if args.artifact_dir else ARTIFACT_ROOT
    out_root.mkdir(parents=True, exist_ok=True)

    if args.plan_only:
        from worldcup_predictor.feature_store.pressure_store.backfill_plan import (
            design_backfill_targets,
            estimate_api_calls,
        )

        target = design_backfill_targets()
        estimate = estimate_api_calls(target)
        print(json.dumps({"target_design": target, "api_estimate": estimate}, indent=2, default=str))
        return 0

    season_id = args.season_id
    use_cache = not args.no_cache

    if args.fixture_id:
        ingest = store.ingest_fixture(
            int(args.fixture_id),
            use_cache=use_cache,
            force_refresh=args.force_refresh,
            force_reimport=args.force_reimport,
        )
        from worldcup_predictor.feature_store.pressure_store.models import PressureIngestResult

        result = PressureIngestResult(
            job_key=args.job_key or f"fixture_{args.fixture_id}",
            fixtures_processed=1,
            fixtures_imported=1 if ingest.get("status") == "imported" else 0,
            records_written=int(ingest.get("records_written") or 0),
        )
        result_dict = {**result.to_dict(), "single_fixture": ingest}
    elif args.manifest:
        manifest_path = Path(args.manifest)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        ids = [int(x["fixture_id"]) for x in payload.get("fixtures", []) if x.get("fixture_id")]
        result = store.backfill_from_fixture_ids(
            ids,
            job_key=args.job_key or "phase54h4_manifest_batch",
            max_calls=args.max_calls,
            use_cache=use_cache,
            force_reimport=args.force_reimport,
        )
        result_dict = result.to_dict()
    elif args.cache_only:
        result = store.backfill_from_cache_dir(
            args.cache_dir or None,
            job_key=args.job_key or f"pressure_cache_l{args.league_id}_s{season_id or 'all'}",
            league_id=args.league_id if args.league_id > 0 else None,
            force_reimport=args.force_reimport,
        )
        result_dict = result.to_dict()
    else:
        result = store.backfill_league(
            league_id=args.league_id,
            season_id=season_id,
            max_calls=args.max_calls,
            job_key=args.job_key or f"phase54h_l{args.league_id}_s{season_id or 'auto'}",
            finished_only=not args.include_upcoming,
            use_cache=use_cache,
            force_refresh=args.force_refresh,
            force_reimport=args.force_reimport,
            dry_run=args.dry_run,
            max_pages=args.max_pages,
        )
        result_dict = result.to_dict()

    audit = store.quality_audit() if not args.dry_run else {}
    out = {
        "backfill": result_dict,
        "audit": audit,
        "postgres_configured": store.configured,
        "league_id": args.league_id,
        "season_id": season_id,
        "cache_only": args.cache_only,
        "dry_run": args.dry_run,
        "options": {
            "cache_first": use_cache,
            "skip_existing": args.skip_existing,
            "save_raw": args.save_raw,
            "include": "participants;pressure;events.type",
            "job_key": args.job_key,
            "resume": args.resume,
        },
    }
    slug = f"l{args.league_id}_s{season_id or 'auto'}"
    job_slug = (args.job_key or slug).replace("/", "_")
    (out_root / f"backfill_{job_slug}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    (out_root / "backfill_result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "fixtures_imported": result_dict.get("fixtures_imported", result_dict.get("single_fixture", {}).get("status")),
                "records_written": result_dict.get("records_written"),
                "audit": audit,
                "postgres_configured": store.configured,
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
