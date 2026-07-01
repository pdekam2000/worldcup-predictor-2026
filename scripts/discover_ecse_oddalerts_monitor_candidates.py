#!/usr/bin/env python3
"""Discover ECSE OddAlerts limited shadow monitor candidates."""

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
from worldcup_predictor.research.oddalerts_ecse_monitor import artifact_paths, discover_monitor_candidates

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", default="2026-07-01")
    parser.add_argument("--date-to", default="2026-07-07")
    args = parser.parse_args()

    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    from worldcup_predictor.research.oddalerts_ecse_monitor import ensure_monitor_table

    ensure_monitor_table(conn)

    result = discover_monitor_candidates(conn, date_from=args.date_from, date_to=args.date_to)
    conn.close()

    paths = artifact_paths(args.date_from, args.date_to)
    paths["candidates"].write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"candidate_count": result["candidate_count"], "skipped": result["skipped_count"]}, indent=2))
    print(f"Written: {paths['candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
