#!/usr/bin/env python3
"""PHASE EURO-A2 — Backfill UEFA fixture_results with improved provider matching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.data_import.european_result_backfill import (
    audit_missing_uefa_results,
    run_uefa_result_backfill,
)

AUDIT_PATH = ROOT / "artifacts" / "euro_a2_missing_uefa_results_audit.json"
SUMMARY_PATH = ROOT / "artifacts" / "euro_a2_result_backfill_repair_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill UEFA fixture_results (EURO-A2 repair)")
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=list(UEFA_CUP_KEYS),
        help="UEFA competition keys",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing fixture_results")
    parser.add_argument("--dry-run", action="store_true", help="Scan only; do not persist results")
    parser.add_argument(
        "--explain-matches",
        action="store_true",
        help="Include per-fixture match resolution details",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max fixtures per competition")
    parser.add_argument("--audit-only", action="store_true", help="Write missing-results audit only")
    parser.add_argument("--audit", type=str, default=str(AUDIT_PATH), help="Audit JSON output path")
    parser.add_argument("--summary", type=str, default=str(SUMMARY_PATH), help="Summary JSON output path")
    args = parser.parse_args()

    audit = audit_missing_uefa_results(
        competition_keys=args.competitions,
        limit=args.limit,
    )
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.audit_only:
        print(json.dumps({"audit_path": str(audit_path), "missing_count": audit["missing_count"]}, indent=2))
        return 0

    report = run_uefa_result_backfill(
        competition_keys=args.competitions,
        force=args.force,
        dry_run=args.dry_run,
        explain=args.explain_matches or args.dry_run,
        limit=args.limit,
    )
    report["audit_path"] = str(audit_path)
    report["audit_missing_count"] = audit["missing_count"]

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
