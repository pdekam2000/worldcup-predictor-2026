#!/usr/bin/env python3
"""PHASE ECSE-1A — Build Exact Correct Score Engine training dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_training_dataset import (
    audit_ecse_training_dataset,
    build_ecse_training_dataset,
    dataset_fingerprint,
    ensure_ecse_training_dataset_table,
)

ARTIFACTS = ROOT / "artifacts"
SUMMARY_PATH = ARTIFACTS / "ecse_1a_build_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ECSE training dataset (ECSE-1A)")
    parser.add_argument("--dry-run", action="store_true", help="Compute stats without writing rows")
    parser.add_argument("--rebuild", action="store_true", help="Delete existing dataset rows before build")
    args = parser.parse_args()

    print("ECSE-1A training dataset build\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_training_dataset_table(conn)

    before = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    stats = build_ecse_training_dataset(conn, dry_run=args.dry_run, rebuild=args.rebuild)
    after = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    audit = audit_ecse_training_dataset(conn)

    summary = {
        "phase": "ECSE-1A",
        "dry_run": args.dry_run,
        "rebuild": args.rebuild,
        "rows_before": before,
        "rows_after": after,
        "build": stats.to_dict(),
        "audit": audit,
        "fingerprint": dataset_fingerprint(conn) if after and not args.dry_run else None,
    }

    if not args.dry_run:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\nDataset rows: {after}")
    if not args.dry_run:
        print(f"Summary written: {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
