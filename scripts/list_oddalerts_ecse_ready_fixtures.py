#!/usr/bin/env python3
"""List ECSE-ready fixtures from OddAlerts CSV promotion (targeted, read-only)."""

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
from worldcup_predictor.research.oddalerts_ecse_dryrun import (
    PROCESS_DATE,
    artifact_paths,
    list_ecse_ready_fixtures,
    load_candidate_fixture_ids,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="List OddAlerts ECSE-ready fixtures")
    parser.add_argument("--date", default=PROCESS_DATE)
    args = parser.parse_args()

    paths = artifact_paths(args.date)
    fixture_ids = load_candidate_fixture_ids(
        dryrun_path=paths["dryrun"],
        write_path=paths["write"],
        write_validation_path=paths["write_validation"],
    )
    if not fixture_ids:
        print(f"No candidate fixture IDs found. Check {paths['dryrun']} and {paths['write']}", file=sys.stderr)
        return 2

    dryrun = json.loads(paths["dryrun"].read_text(encoding="utf-8")) if paths["dryrun"].exists() else {}
    dryrun_candidates = {
        int(c["fixture_id"]): c for c in (dryrun.get("candidates") or []) if c.get("fixture_id") is not None
    }

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=60)
    conn.row_factory = sqlite3.Row

    result = list_ecse_ready_fixtures(conn, fixture_ids, dryrun_candidates=dryrun_candidates)
    result["date_processed"] = args.date
    result["source_fixture_id_count"] = len(fixture_ids)
    conn.close()

    paths["fixture_list"].parent.mkdir(parents=True, exist_ok=True)
    paths["fixture_list"].write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "fixture_count": result["fixture_count"],
                "skipped_count": result["skipped_count"],
                "source_ids": len(fixture_ids),
            },
            indent=2,
        )
    )
    print(f"Written: {paths['fixture_list']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
