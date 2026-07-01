#!/usr/bin/env python3
"""PHASE ECSE-1C — Build lambda features for ECSE training fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_lambda_extraction import (
    METHOD_VERSION,
    audit_ecse_lambda_features,
    build_ecse_lambda_features,
    ensure_ecse_lambda_features_table,
    lambda_fingerprint,
)

SUMMARY_PATH = ROOT / "artifacts" / "ecse_1c_lambda_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-1C lambda extraction")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    print("ECSE-1C lambda extraction\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_lambda_features_table(conn)

    before = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    stats = build_ecse_lambda_features(conn, dry_run=args.dry_run, rebuild=args.rebuild)
    after = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    audit = audit_ecse_lambda_features(conn)

    summary = {
        "phase": "ECSE-1C",
        "method_version": METHOD_VERSION,
        "dry_run": args.dry_run,
        "rebuild": args.rebuild,
        "rows_before": before,
        "rows_after": after,
        "build": stats.to_dict(),
        "audit": audit,
        "fingerprint": lambda_fingerprint(conn) if after and not args.dry_run else None,
    }

    if not args.dry_run:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\necse_lambda_features rows: {after}")
    if not args.dry_run:
        print(f"Summary: {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
