#!/usr/bin/env python3
"""PHASE ODDALERTS-CSV-PLAYER-REF-1 — Inspect OddAlerts CSV type/schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_enrichment_csv_importer import (
    INBOX_DIR,
    SCHEMA_PROFILE_PATH,
    inspect_csv_paths,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect OddAlerts CSV files")
    parser.add_argument("paths", nargs="*", help="CSV paths (default: inbox/*.csv)")
    args = parser.parse_args()

    if args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        paths = sorted(INBOX_DIR.glob("*.csv"))

    if not paths:
        print(f"No CSV files found in {INBOX_DIR}")
        return 1

    profile = inspect_csv_paths(paths)
    print(json.dumps(profile, indent=2, ensure_ascii=False))
    print(f"Written: {SCHEMA_PROFILE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
