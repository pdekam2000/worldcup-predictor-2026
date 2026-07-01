#!/usr/bin/env python3
"""Evaluate ECSE OddAlerts shadow predictions (artifact only)."""

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
    evaluate_shadow_predictions,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate ECSE OddAlerts shadow predictions")
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    args = parser.parse_args()

    paths = artifact_paths(args.date)
    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row

    evaluation = evaluate_shadow_predictions(conn, shadow_run_id=args.run_id)
    conn.close()

    paths["evaluation"].write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evaluation, indent=2))
    print(f"Written: {paths['evaluation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
