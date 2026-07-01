#!/usr/bin/env python3
"""Write ECSE OddAlerts dry-run outputs to shadow table (owner/internal)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.research.oddalerts_ecse_shadow import (
    DEFAULT_RUN_ID,
    PROCESS_DATE,
    artifact_paths,
    load_dryrun_records,
    write_shadow_predictions,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Write ECSE OddAlerts shadow predictions")
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fixture-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--write", action="store_true", default=False)
    args = parser.parse_args()

    dry_run = not args.write
    paths = artifact_paths(args.date)
    input_path = args.input or paths["predictions_jsonl"]
    if not input_path.exists():
        print(f"Missing input: {input_path}", file=sys.stderr)
        return 2

    records = load_dryrun_records(input_path, limit=args.limit, fixture_id=args.fixture_id)
    db_path = get_db_path(get_settings().sqlite_path)

    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row

    ecse_before = _count(conn, "ecse_prediction_snapshots")
    odds_before = _count(conn, "odds_snapshots")
    wde_before = _count(conn, "worldcup_stored_predictions")

    result = write_shadow_predictions(
        conn,
        records,
        shadow_run_id=args.run_id,
        dry_run=dry_run,
    )

    ecse_after = _count(conn, "ecse_prediction_snapshots")
    odds_after = _count(conn, "odds_snapshots")
    wde_after = _count(conn, "worldcup_stored_predictions")
    conn.close()

    out = {
        **result,
        "date_processed": args.date,
        "input_path": str(input_path),
        "ecse_snapshots_before": ecse_before,
        "ecse_snapshots_after": ecse_after,
        "odds_snapshots_before": odds_before,
        "odds_snapshots_after": odds_after,
        "wde_predictions_before": wde_before,
        "wde_predictions_after": wde_after,
    }
    paths["write_out"].write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(out, indent=2))
    print(f"Written: {paths['write_out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
