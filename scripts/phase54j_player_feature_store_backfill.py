#!/usr/bin/env python3
"""Phase 54J — Lineup / player feature store cache backfill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54j_player_feature_store"


def main() -> int:
    parser = argparse.ArgumentParser(description="Player feature store cache backfill")
    parser.add_argument("--league-id", type=int, default=0, help="0 = all target leagues")
    parser.add_argument("--cache-dir", type=str, default="")
    parser.add_argument("--job-key", type=str, default="phase54j_cache_import")
    parser.add_argument("--force-reimport", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Count cache files only")
    args = parser.parse_args()

    from worldcup_predictor.feature_store.player_store.normalizers import normalize_fixture_player_stats
    from worldcup_predictor.feature_store.player_store.player_feature_store import PlayerFeatureStore, _CACHE_ROOTS

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        counts = {"files": 0, "with_lineups": 0, "players": 0}
        roots = [Path(args.cache_dir)] if args.cache_dir else list(_CACHE_ROOTS)
        seen: set[int] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.glob("*.json"):
                try:
                    blob = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                data = (blob.get("payload") or {}).get("data")
                if not isinstance(data, dict):
                    continue
                sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
                if sm_id in seen:
                    continue
                seen.add(sm_id)
                if args.league_id and int(data.get("league_id") or 0) != args.league_id:
                    continue
                counts["files"] += 1
                recs = normalize_fixture_player_stats(data, sportmonks_fixture_id=sm_id)
                if recs:
                    counts["with_lineups"] += 1
                    counts["players"] += len(recs)
        print(json.dumps(counts, indent=2))
        (ARTIFACT_DIR / "dry_run.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
        return 0

    store = PlayerFeatureStore()
    cache_dirs = [Path(args.cache_dir)] if args.cache_dir else None
    league_id = args.league_id if args.league_id else None

    result = store.backfill_from_cache(
        cache_dirs=cache_dirs,
        league_id=league_id,
        job_key=args.job_key,
        force_reimport=args.force_reimport,
    )

    audit = store.coverage_audit()
    readiness = store.goalscorer_readiness_matrix(audit)
    recommendation = store.recommend_next(audit)

    out = {
        "backfill": result.to_dict(),
        "coverage_audit": audit,
        "goalscorer_readiness": readiness,
        "recommendation": recommendation,
        "postgres_configured": store.configured,
    }
    (ARTIFACT_DIR / "backfill_result.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    (ARTIFACT_DIR / "goalscorer_readiness.json").write_text(json.dumps(readiness, indent=2), encoding="utf-8")

    print(json.dumps({"recommendation": recommendation, "audit": audit.get("match_stats")}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
