#!/usr/bin/env python3
"""Import external historical CSV ZIP into staging tables only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.external_historical_zip_importer import (  # noqa: E402
    INBOX_DIR,
    IMPORT_SUMMARY_PATH,
    import_zip,
    write_import_summary,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import external historical CSV ZIP")
    parser.add_argument("--zip", type=Path, default=INBOX_DIR / "historical_csv_data.zip")
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default when --stage-only omitted)")
    parser.add_argument("--stage-only", action="store_true", help="Write raw + normalized staging tables")
    args = parser.parse_args()

    dry_run = not args.stage_only
    stage_only = args.stage_only

    if not args.zip.is_file():
        print(json.dumps({"error": f"ZIP not found: {args.zip}"}, indent=2))
        return 2

    conn = connect(get_settings().sqlite_path)
    batch = import_zip(conn, args.zip.resolve(), dry_run=dry_run, stage_only=stage_only)
    if not dry_run:
        conn.commit()
    conn.close()

    write_import_summary(batch)
    print(json.dumps({k: batch.to_dict()[k] for k in batch.to_dict() if k != "files"}, indent=2, ensure_ascii=False))
    print(f"Written: {IMPORT_SUMMARY_PATH}")
    return 1 if batch.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
