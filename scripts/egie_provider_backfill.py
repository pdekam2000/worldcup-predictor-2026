#!/usr/bin/env python3
"""Phase API-F — cache-first paid provider backfill for EGIE PL fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "artifacts" / "egie_provider_backfill_result.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="EGIE provider backfill (API-F)")
    parser.add_argument("--providers", default="sportmonks,api_football", help="Comma-separated providers")
    parser.add_argument("--limit-fixtures", type=int, default=380)
    parser.add_argument("--max-api-calls", type=int, default=80)
    parser.add_argument("--mapping-only", action="store_true", help="Run mapping audit only")
    parser.add_argument("--skip-rebuild", action="store_true")
    parser.add_argument("--fixture-ids", type=str, default="", help="Comma-separated fixture ids")
    args = parser.parse_args()

    providers = tuple(p.strip() for p in args.providers.split(",") if p.strip())
    fixture_ids = [int(x) for x in args.fixture_ids.split(",") if x.strip().isdigit()] or None

    from worldcup_predictor.egie.backfill.orchestrator import ProviderBackfillOrchestrator

    orch = ProviderBackfillOrchestrator()
    result = orch.run(
        providers=providers,
        limit_fixtures=args.limit_fixtures,
        max_api_calls=args.max_api_calls,
        fixture_ids=fixture_ids,
        skip_backfill=args.mapping_only,
        rebuild_survival=not args.skip_rebuild,
        audit_utilization=True,
    )

    payload = result.to_dict()
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    mapping_path = ROOT / "artifacts" / "egie_provider_fixture_mapping_audit.json"
    mapping_path.write_text(json.dumps(payload.get("mapping_audit") or {}, indent=2, default=str), encoding="utf-8")

    print(json.dumps(
        {
            "artifact": str(ARTIFACT),
            "mapping_artifact": str(mapping_path),
            "sportmonks_api_calls": (payload.get("sportmonks") or {}).get("api_calls_live"),
            "api_football_api_calls": (payload.get("api_football") or {}).get("api_calls_live"),
            "pl_odds_after": (payload.get("api_football") or {}).get("pl_odds_snapshot_fixtures"),
            "utilization_after": (payload.get("utilization_after") or {}).get("provider_feature_store", {}).get("coverage_pct"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
