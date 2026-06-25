#!/usr/bin/env python3
"""Phase API-H — UEFA club EGIE Sportmonks dataset pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
COVERAGE_PATH = ARTIFACTS / "uefa_club_league_coverage.json"
MAPPING_PATH = ARTIFACTS / "uefa_fixture_mapping.json"
BACKTEST_PATH = ARTIFACTS / "uefa_club_backtest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase API-H UEFA club EGIE pipeline")
    parser.add_argument("--max-api-calls", type=int, default=150)
    parser.add_argument("--limit-per-league", type=int, default=40)
    parser.add_argument("--skip-ingest", action="store_true")
    args = parser.parse_args()

    from worldcup_predictor.egie.uefa_club.league_coverage import audit_uefa_league_coverage
    from worldcup_predictor.egie.uefa_club.fixture_mapping import build_uefa_fixture_mapping
    from worldcup_predictor.egie.uefa_club.sportmonks_ingest import ingest_uefa_sportmonks_features
    from worldcup_predictor.egie.uefa_club.sqlite_bridge import sync_uefa_fixtures_to_sqlite
    from worldcup_predictor.egie.uefa_club.feature_store import UefaClubFeatureStore
    from worldcup_predictor.egie.uefa_club.survival_dataset import UefaSurvivalDatasetBuilder
    from worldcup_predictor.egie.uefa_club.backtest_runner import UefaClubBacktestRunner

    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    coverage = audit_uefa_league_coverage(max_pages_per_league=3)
    COVERAGE_PATH.write_text(json.dumps(coverage, indent=2, default=str), encoding="utf-8")
    print(f"STEP 1 coverage -> {COVERAGE_PATH} ({coverage.get('total_fixtures_sampled')} sampled)")

    mapping = build_uefa_fixture_mapping(
        limit_per_league=args.limit_per_league,
        finished_only=True,
    )
    MAPPING_PATH.write_text(json.dumps(mapping, indent=2, default=str), encoding="utf-8")
    fixtures = mapping.get("fixtures") or []
    print(f"STEP 2 mapping -> {MAPPING_PATH} ({len(fixtures)} fixtures)")

    ingest_result = {"skipped": True}
    if not args.skip_ingest and fixtures:
        ingest_result = ingest_uefa_sportmonks_features(
            fixtures,
            max_api_calls=args.max_api_calls,
        )
        print(f"STEP 3 ingest: {json.dumps(ingest_result)}")

    bridge = sync_uefa_fixtures_to_sqlite(fixtures)
    print(f"STEP 3b sqlite bridge: {json.dumps(bridge)}")

    store = UefaClubFeatureStore()
    ids = [int(f["sportmonks_fixture_id"]) for f in fixtures]
    utilization = store.audit_utilization(ids, competition_key="champions_league")
    print(f"STEP 4 provider coverage: {json.dumps(utilization)}")

    survival_path = UefaSurvivalDatasetBuilder().build_and_save(fixtures)
    print(f"STEP 5 survival -> {survival_path}")

    backtest = UefaClubBacktestRunner().run(fixtures)
    slim = {k: v for k, v in backtest.items() if k != "per_strategy_results"}
    BACKTEST_PATH.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "uefa_club_backtest_full.json").write_text(
        json.dumps(backtest, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"STEP 6 backtest -> {BACKTEST_PATH}")
    print(json.dumps(slim, indent=2))

    from scripts._write_phase_api_h_report import write_report

    write_report(
        coverage=coverage,
        mapping=mapping,
        ingest=ingest_result,
        utilization=utilization,
        backtest=slim,
        survival_path=str(survival_path),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
