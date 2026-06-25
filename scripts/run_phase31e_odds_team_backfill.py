#!/usr/bin/env python3
"""Phase 31E — team ID + historical odds backfill from cache."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.backtesting.phase31e_backfill import (  # noqa: E402
    run_phase31e,
    write_phase31e_report,
)

ARTIFACT = ROOT / "artifacts" / "phase31e_odds_backfill_summary.json"
REPORT = ROOT / "PHASE_31E_HISTORICAL_ODDS_TEAM_ID_BACKFILL_REPORT.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 31E odds + team ID backfill")
    parser.add_argument("--db", default=str(ROOT / "data" / "football_intelligence.db"))
    parser.add_argument("--skip-replay", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = run_phase31e(db_path=args.db, skip_replay=args.skip_replay)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_phase31e_report(result, REPORT)

    team = result["team_id_backfill"]
    backfill = result["odds_backfill"]
    print(f"Team IDs updated: {team['rows_updated']}/{team['rows_scanned']}")
    print(f"Odds backfill: {backfill['odds_snapshots_created']} snapshots, {backfill['fixture_enrichment_odds_updated']} enrichment")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
