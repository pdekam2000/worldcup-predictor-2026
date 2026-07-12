#!/usr/bin/env python3
"""Orchestrate prematch feature coverage backfill phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.provider_features.backfill_runner import run_pilot_backfill
from worldcup_predictor.provider_features.coverage import measure_coverage
from worldcup_predictor.provider_features.entitlements import verify_entitlements
from worldcup_predictor.provider_features.live_shadow_runner import prepare_live_shadow_runner
from worldcup_predictor.provider_features.report_generator import generate_all_reports
from worldcup_predictor.provider_features.repository import ensure_tables


def main() -> int:
    parser = argparse.ArgumentParser(description="Prematch feature coverage backfill phase")
    parser.add_argument("--dry-run", action="store_true", help="Plans and stored-data only, no API")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--max-api-calls", type=int, default=50)
    parser.add_argument("--max-sportmonks-calls", type=int, default=50)
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_tables(conn)
    conn.close()

    report: dict = {"phase": "PREMATCH-FEATURE-COVERAGE-BACKFILL", "steps": {}}
    report["steps"]["entitlements_dry"] = verify_entitlements(dry_run=True)
    if not args.dry_run:
        report["steps"]["entitlements_live"] = verify_entitlements(dry_run=False)

    if not args.skip_backfill:
        report["steps"]["pilot_backfill"] = run_pilot_backfill(
            settings=settings,
            dry_run=args.dry_run,
            max_api_calls=args.max_api_calls,
            max_sportmonks_calls=args.max_sportmonks_calls,
        )

    report["steps"]["live_shadow_prep"] = prepare_live_shadow_runner()
    report["steps"]["coverage"] = measure_coverage(connect(settings.sqlite_path))
    report["steps"]["reports"] = generate_all_reports()
    report["production_modified"] = False

    out = ROOT / "artifacts/prematch_feature_backfill/run_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
