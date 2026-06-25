#!/usr/bin/env python3
"""Phase 54E/54F-4 — Sportmonks xG feature store backfill (cache-first, resumable)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "artifacts" / "phase54e_sportmonks_xg_feature_store"


def _parse_metric_keys(values: list[str] | None) -> tuple[frozenset[str] | None, bool]:
    if not values:
        return None, False
    keys = frozenset(v.strip().lower() for v in values if v.strip())
    require_team_xg = "xg" in keys
    return keys if len(keys) > 1 or not require_team_xg else None, require_team_xg


def main() -> int:
    parser = argparse.ArgumentParser(description="Sportmonks xG feature store backfill")
    parser.add_argument("--league-id", type=int, default=732)
    parser.add_argument("--season-id", type=int, default=None)
    parser.add_argument("--season-label", type=str, default="", help="e.g. 2026, 2024/2025")
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--max-pages", type=int, default=15)
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--cache-first", action="store_true", default=True)
    parser.add_argument("--no-cache", action="store_true", help="Disable cache-first reads")
    parser.add_argument("--cache-dir", type=str, default="")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--force-reimport", action="store_true")
    parser.add_argument("--include-upcoming", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--save-raw", action="store_true", default=True)
    parser.add_argument("--job-key", type=str, default="")
    parser.add_argument("--metric-key", action="append", default=None)
    args = parser.parse_args()

    from worldcup_predictor.feature_store.sportmonks_xg_store import SportmonksXgFeatureStore

    metric_keys, require_team_xg = _parse_metric_keys(args.metric_key)
    store = SportmonksXgFeatureStore()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    season_id = args.season_id
    if args.season_label and not season_id:
        season_id = store.resolve_season_id_by_label(args.league_id, args.season_label)
        if season_id is None:
            out = {"error": f"season_label_not_found:{args.season_label}", "league_id": args.league_id}
            print(json.dumps(out, indent=2))
            return 1

    use_cache = not args.no_cache

    if args.cache_only:
        result = store.backfill_from_cache_dir(
            args.cache_dir or None,
            job_key=args.job_key or f"xg_cache_l{args.league_id}_s{season_id or 'all'}",
            league_id=args.league_id if args.league_id > 0 else None,
            force_reimport=args.force_reimport,
            metric_keys=metric_keys,
            require_team_xg=require_team_xg,
        )
    else:
        result = store.backfill_league(
            league_id=args.league_id,
            season_id=season_id,
            max_calls=args.max_calls,
            job_key=args.job_key or f"phase54f4_l{args.league_id}_s{season_id or args.season_label or 'auto'}",
            finished_only=not args.include_upcoming,
            use_cache=use_cache,
            force_refresh=args.force_refresh,
            force_reimport=args.force_reimport,
            metric_keys=metric_keys,
            require_team_xg=require_team_xg,
            dry_run=args.dry_run,
            max_pages=args.max_pages,
        )

    audit = store.quality_audit() if not args.dry_run else {}
    out = {
        "backfill": result.to_dict(),
        "audit": audit,
        "postgres_configured": store.configured,
        "league_id": args.league_id,
        "season_id": season_id,
        "season_label": args.season_label or None,
        "metric_key_filter": sorted(metric_keys) if metric_keys else None,
        "require_team_xg": require_team_xg,
        "dry_run": args.dry_run,
    }
    slug = f"l{args.league_id}_s{season_id or args.season_label or 'auto'}"
    (ARTIFACT_ROOT / f"backfill_{slug}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_ROOT / "backfill_result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
