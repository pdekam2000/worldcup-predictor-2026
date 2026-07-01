#!/usr/bin/env python3
"""Incremental OddAlerts inbox CSV import — stage probability CSVs, import enrichment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_csv_incremental_importer import (
    IMPORT_SUMMARY_PATH,
    INBOX_DIR,
    import_inbox_incremental,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental OddAlerts inbox CSV import")
    parser.add_argument("--input-dir", type=Path, default=INBOX_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = connect(get_settings().sqlite_path)
    batch = import_inbox_incremental(conn, input_dir=args.input_dir.resolve(), dry_run=args.dry_run)
    conn.close()

    summary = batch.to_dict()
    if IMPORT_SUMMARY_PATH.exists():
        summary = json.loads(IMPORT_SUMMARY_PATH.read_text(encoding="utf-8"))

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Written: {IMPORT_SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
