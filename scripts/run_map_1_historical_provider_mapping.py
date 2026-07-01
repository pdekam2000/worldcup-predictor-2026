#!/usr/bin/env python3
"""PHASE MAP-1 — Build historical provider mappings (read-only, no API)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.historical_provider_mapping import (
    PROVIDERS,
    audit_mappings,
    build_api_football_candidates,
    build_historical_provider_mappings,
    build_oddalerts_candidates,
    build_sportmonks_candidates,
    mapping_report_md,
)

REPORT_PATH = ROOT / "HISTORICAL_PROVIDER_MAPPING_REPORT.md"
SUMMARY_PATH = ROOT / "artifacts" / "provider_mapping_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="MAP-1 historical provider mapping")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-upgrade", action="store_true", help="Do not replace lower-confidence mappings")
    args = parser.parse_args()

    print("MAP-1 historical provider mapping\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    candidate_counts = {
        "api_football": len(build_api_football_candidates(conn)),
        "sportmonks": len(build_sportmonks_candidates(conn)),
        "oddalerts": len(build_oddalerts_candidates(conn)),
    }
    print("Local candidate pools:", json.dumps(candidate_counts, indent=2))

    stats = build_historical_provider_mappings(
        conn,
        dry_run=args.dry_run,
        upgrade_better=not args.no_upgrade,
    )
    audit = audit_mappings(conn)
    conn.close()

    payload = {
        "phase": "MAP-1",
        "dry_run": args.dry_run,
        "providers": list(PROVIDERS),
        "candidate_counts": candidate_counts,
        "build": stats.to_dict(),
        "audit": audit,
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(mapping_report_md(stats, audit, candidate_counts), encoding="utf-8")

    print(json.dumps({"build": stats.to_dict(), "audit": audit}, indent=2))
    print(f"\nReport: {REPORT_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
