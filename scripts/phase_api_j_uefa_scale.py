#!/usr/bin/env python3
"""Phase API-J — historical xG availability + UEFA EGIE scale validation."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
MAPPING_PATH = ARTIFACTS / "uefa_fixture_mapping.json"
MAPPING_API_I = ARTIFACTS / "uefa_fixture_mapping_api_i.json"
BACKTEST_PATH = ARTIFACTS / "uefa_club_backtest.json"
BACKTEST_API_I = ARTIFACTS / "uefa_club_backtest_api_i_before.json"


def _snapshot_api_i() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if MAPPING_PATH.is_file() and not MAPPING_API_I.is_file():
        shutil.copy2(MAPPING_PATH, MAPPING_API_I)
    if BACKTEST_PATH.is_file() and not BACKTEST_API_I.is_file():
        shutil.copy2(BACKTEST_PATH, BACKTEST_API_I)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase API-J UEFA scale validation")
    parser.add_argument("--max-reingest", type=int, default=20)
    parser.add_argument("--max-expand-api", type=int, default=35)
    parser.add_argument("--max-ingest-api", type=int, default=80)
    parser.add_argument("--skip-live-audit", action="store_true")
    args = parser.parse_args()

    _snapshot_api_i()

    from worldcup_predictor.egie.uefa_club.historical_availability import (
        audit_historical_predictions_availability,
        audit_historical_xg_availability,
    )
    from worldcup_predictor.egie.uefa_club.pending_audit import audit_pending_fixtures
    from worldcup_predictor.egie.uefa_club.targeted_reingest import (
        expand_uefa_fixture_mapping,
        targeted_reingest_uefa,
    )
    from worldcup_predictor.egie.uefa_club.sportmonks_ingest import ingest_uefa_sportmonks_features
    from worldcup_predictor.egie.uefa_club.sqlite_bridge import sync_uefa_fixtures_to_sqlite
    from worldcup_predictor.egie.uefa_club.feature_store import UefaClubFeatureStore
    from worldcup_predictor.egie.uefa_club.survival_dataset import UefaSurvivalDatasetBuilder
    from worldcup_predictor.egie.uefa_club.backtest_runner import UefaClubBacktestRunner
    from worldcup_predictor.egie.uefa_club.feature_impact import rank_feature_impact

    before_mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8")) if MAPPING_PATH.is_file() else {"fixtures": []}
    before_count = len(before_mapping.get("fixtures") or [])
    before_bt = json.loads(BACKTEST_API_I.read_text(encoding="utf-8")) if BACKTEST_API_I.is_file() else {}

    # STEP 1-2: Historical availability audits
    if args.skip_live_audit:
        xg_audit = {"skipped": True, "cache_only": True}
        pred_audit = {"skipped": True}
    else:
        xg_audit = audit_historical_xg_availability(max_live_probes=12)
        pred_audit = audit_historical_predictions_availability(max_live_probes=9)
    (ARTIFACTS / "historical_xg_availability_audit.json").write_text(
        json.dumps(xg_audit, indent=2, default=str), encoding="utf-8"
    )
    (ARTIFACTS / "historical_predictions_availability_audit.json").write_text(
        json.dumps(pred_audit, indent=2, default=str), encoding="utf-8"
    )
    print("STEP 1-2 historical audits written")

    fixtures = before_mapping.get("fixtures") or []

    # STEP 3: Pending audit (pre-reingest)
    pending = audit_pending_fixtures(fixtures)
    (ARTIFACTS / "uefa_pending_fixture_root_causes.json").write_text(
        json.dumps(pending, indent=2, default=str), encoding="utf-8"
    )
    print(f"STEP 3 pending audit: {pending.get('summary')}")

    # STEP 4: Targeted re-ingest
    candidates = pending.get("reingest_candidates") or []
    reingest = targeted_reingest_uefa(fixtures, candidates, max_api_calls=args.max_reingest)
    (ARTIFACTS / "uefa_targeted_reingest_result.json").write_text(
        json.dumps(reingest, indent=2, default=str), encoding="utf-8"
    )
    print(f"STEP 4 re-ingest: api={reingest.get('api_calls_used')} recovered_events={reingest.get('recovered_events')}")

    # STEP 5: Sample expansion
    expanded = expand_uefa_fixture_mapping(
        before_mapping,
        max_api_calls=args.max_expand_api,
        per_season_limit=25,
    )
    MAPPING_PATH.write_text(json.dumps(expanded, indent=2, default=str), encoding="utf-8")
    fixtures = expanded.get("fixtures") or []
    after_count = len(fixtures)

    sample_size = {
        "before": {
            "mapping_fixtures": before_count,
            "backtest_eligible_a": ((before_bt.get("strategies") or {}).get("A") or {}).get("coverage", {}).get("eligible"),
            "fg_team_pending_a": (
                ((before_bt.get("strategies") or {}).get("A") or {})
                .get("metrics", {})
                .get("by_market", {})
                .get("first_goal_team", {})
                .get("pending")
            ),
        },
        "after_mapping": {
            "mapping_fixtures": after_count,
            "added": after_count - before_count,
            "by_competition": expanded.get("by_competition_key"),
        },
    }
    print(f"STEP 5 mapping expanded {before_count} -> {after_count}")

    # Ingest new fixtures only (cache-first)
    ingest = ingest_uefa_sportmonks_features(fixtures, max_api_calls=args.max_ingest_api)
    print(f"STEP 5b ingest: {json.dumps(ingest)}")

    # STEP 6: Rebuild
    bridge = sync_uefa_fixtures_to_sqlite(fixtures)
    store = UefaClubFeatureStore()
    ids = [int(f["sportmonks_fixture_id"]) for f in fixtures]
    utilization = store.audit_utilization(ids, competition_key="champions_league")
    survival_path = UefaSurvivalDatasetBuilder().build_and_save(fixtures)

    # Update sample size with coverage
    sample_size["after_rebuild"] = {
        "provider_coverage_pct": utilization.get("coverage_pct"),
        "survival_dataset": str(survival_path),
        "sqlite_upserted": bridge.get("upserted"),
    }
    (ARTIFACTS / "before_vs_after_sample_size.json").write_text(
        json.dumps(sample_size, indent=2, default=str), encoding="utf-8"
    )

    # STEP 7: Backtest
    backtest = UefaClubBacktestRunner().run(fixtures)
    slim = {k: v for k, v in backtest.items() if k != "per_strategy_results"}
    BACKTEST_PATH.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
    (ARTIFACTS / "uefa_club_backtest_full.json").write_text(
        json.dumps(backtest, indent=2, default=str), encoding="utf-8"
    )

    # Re-run pending audit post-fix
    pending_after = audit_pending_fixtures(fixtures, backtest_path=ARTIFACTS / "uefa_club_backtest_full.json")
    pending["after_reingest_summary"] = pending_after.get("summary")
    pending["reingest_result"] = {
        "api_calls": reingest.get("api_calls_used"),
        "recovered_events": reingest.get("recovered_events"),
    }
    (ARTIFACTS / "uefa_pending_fixture_root_causes.json").write_text(
        json.dumps(pending, indent=2, default=str), encoding="utf-8"
    )

    # STEP 8: Feature impact
    impact = rank_feature_impact(slim)
    (ARTIFACTS / "uefa_feature_impact_ranking.json").write_text(
        json.dumps(impact, indent=2, default=str), encoding="utf-8"
    )

    api_total = (
        int(reingest.get("api_calls_used") or 0)
        + int(ingest.get("api_calls_live") or 0)
        + int(expanded.get("api_calls_made", 0) - int(before_mapping.get("api_calls_made") or 0))
        + int((xg_audit.get("live_probe") or {}).get("api_calls") or 0)
        + int((pred_audit.get("live_probes") or {}).get("api_calls") or 0)
    )

    # Validations
    import subprocess

    subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_egie_uefa_club_dataset.py")], check=False)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_uefa_event_team_mapping.py")], check=False)

    from scripts._write_phase_api_j_report import write_report

    write_report(
        xg_audit=xg_audit,
        pred_audit=pred_audit,
        pending=pending,
        reingest=reingest,
        sample_size=sample_size,
        utilization=utilization,
        backtest=slim,
        impact=impact,
        api_total=api_total,
        before_bt=before_bt,
    )
    print(f"STEP 9 report written. API calls ~{api_total}")
    print(json.dumps(slim, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
