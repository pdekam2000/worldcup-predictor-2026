#!/usr/bin/env python3
"""PHASE ECSE-WC-2 — Run knockout draw/PEN risk evaluation + optional penalty backfill."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_live.result_sync import backfill_penalty_metadata_for_fixtures
from worldcup_predictor.research.ecse_wc.knockout_draw_pen_risk import (
    RISK_JSONL,
    RISK_SUMMARY,
    run_knockout_draw_pen_risk_evaluation,
)

WC_PEN_FIXTURES = (1565176, 1562345, 1562344)


def _backfill_penalty_scores(
    *,
    fixture_ids: list[int] | None = None,
    dry_run: bool = False,
) -> dict:
    settings = get_settings()
    ids = list(fixture_ids or WC_PEN_FIXTURES)
    backfill = backfill_penalty_metadata_for_fixtures(
        settings=settings,
        fixture_ids=ids,
        dry_run=dry_run,
    )
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        rows = []
        for fid in fixture_ids or WC_PEN_FIXTURES:
            row = conn.execute(
                """
                SELECT fixture_id, final_score, match_outcome_type, penalty_score
                FROM fixture_results WHERE fixture_id = ?
                """,
                (fid,),
            ).fetchone()
            if row:
                rows.append(dict(row))
    finally:
        conn.close()
    return {
        "backfill": backfill,
        "fixture_results": rows,
        "evaluations_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-WC-2 knockout draw/PEN risk evaluation")
    parser.add_argument("--competition", default="world_cup_2026")
    parser.add_argument("--skip-penalty-backfill", action="store_true")
    parser.add_argument("--penalty-backfill-dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    penalty_backfill: dict = {"skipped": True}
    if not args.skip_penalty_backfill:
        penalty_backfill = _backfill_penalty_scores(dry_run=args.penalty_backfill_dry_run)

    try:
        result = run_knockout_draw_pen_risk_evaluation(
            conn,
            competition_key=args.competition,
            settings=settings,
            penalty_backfill=penalty_backfill,
        )
    finally:
        conn.close()

    payload = result.summary
    if args.json_out:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {RISK_JSONL}")
    print(f"Wrote {RISK_SUMMARY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
