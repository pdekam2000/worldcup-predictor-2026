#!/usr/bin/env python3
"""Evaluate ECSE OddAlerts limited shadow monitor records."""

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
from worldcup_predictor.research.oddalerts_ecse_monitor import (
    artifact_paths,
    evaluate_monitor_records,
    monitor_run_id,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", default="2026-07-01")
    parser.add_argument("--date-to", default="2026-07-07")
    args = parser.parse_args()

    paths = artifact_paths(args.date_from, args.date_to)
    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row

    evaluation = evaluate_monitor_records(
        conn,
        date_from=args.date_from,
        date_to=args.date_to,
        monitor_run_id_val=monitor_run_id(args.date_from, args.date_to),
    )
    conn.close()

    paths["evaluation"].write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evaluation, indent=2))
    print(f"Written: {paths['evaluation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
