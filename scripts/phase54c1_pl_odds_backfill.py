#!/usr/bin/env python3
"""Phase 54C-1 — dedicated Premier League odds-only backfill."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "phase54c1_pl_odds_backfill_result.json"
MANIFEST = ROOT / "data" / "shadow" / "phase54c1_pl_odds_backfill_manifest.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54C-1 PL odds-only backfill")
    parser.add_argument("--league-id", type=int, default=None, help="Filter fixtures by league_id (default: 39)")
    parser.add_argument("--season", type=int, default=None, help="Filter fixtures by season (default: competition season)")
    parser.add_argument("--limit-fixtures", type=int, default=380)
    parser.add_argument("--max-api-calls", type=int, default=400)
    parser.add_argument("--fixture-ids", type=str, default="", help="Comma-separated fixture ids")
    parser.add_argument("--manifest", type=str, default=str(MANIFEST))
    parser.add_argument("--artifact", type=str, default=str(ARTIFACT))
    args = parser.parse_args()

    fixture_ids = [int(x) for x in args.fixture_ids.split(",") if x.strip().isdigit()] or None

    from worldcup_predictor.egie.backfill.api_football_provider_backfill import run_pl_odds_backfill
    from worldcup_predictor.egie.provider_features.audit import audit_egie_paid_provider_utilization

    utilization_before = audit_egie_paid_provider_utilization(
        competition_key="premier_league",
        limit=args.limit_fixtures or 400,
    )

    started_at = datetime.now(timezone.utc).isoformat()
    result = run_pl_odds_backfill(
        fixture_ids=fixture_ids,
        limit_fixtures=args.limit_fixtures,
        max_api_calls=args.max_api_calls,
        league_id=args.league_id,
        season=args.season,
        manifest_path=Path(args.manifest),
    )

    utilization_after = audit_egie_paid_provider_utilization(
        competition_key="premier_league",
        limit=args.limit_fixtures or 400,
    )

    payload = {
        "started_at": started_at,
        "finished_at": result.get("finished_at"),
        "args": {
            "league_id": args.league_id,
            "season": args.season,
            "limit_fixtures": args.limit_fixtures,
            "max_api_calls": args.max_api_calls,
            "fixture_ids": fixture_ids,
        },
        "backfill": result,
        "utilization_before": utilization_before,
        "utilization_after": utilization_after,
    }

    artifact_path = Path(args.artifact)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    before = result.get("pl_odds_fixtures_before", 0)
    after = result.get("pl_odds_fixtures_after", 0)
    cov_before = (utilization_before.get("provider_feature_store") or {}).get("coverage_pct", {}).get("odds", 0)
    cov_after = (utilization_after.get("provider_feature_store") or {}).get("coverage_pct", {}).get("odds", 0)

    print(
        json.dumps(
            {
                "artifact": str(artifact_path),
                "manifest": result.get("manifest_path"),
                "fixtures_scanned": result.get("targets"),
                "api_calls_live": result.get("api_calls_live"),
                "api_calls_cache": result.get("api_calls_cache"),
                "snapshots_created": result.get("odds_snapshots_created"),
                "pl_odds_before": before,
                "pl_odds_after": after,
                "egie_odds_coverage_before_pct": cov_before,
                "egie_odds_coverage_after_pct": cov_after,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
