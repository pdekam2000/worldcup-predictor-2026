#!/usr/bin/env python3
"""PHASE ECSE-1D — Build Poisson score distributions from lambda features."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_score_distribution import (
    METHOD_VERSION,
    audit_ecse_score_distributions,
    build_ecse_score_distributions,
    distribution_fingerprint,
    ensure_ecse_score_distributions_table,
    sample_top_n_summary,
)

SUMMARY_PATH = ROOT / "artifacts" / "ecse_1d_distribution_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-1D score distribution build")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    print("ECSE-1D score distribution build\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_score_distributions_table(conn)

    fixtures_before = conn.execute(
        "SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_score_distributions"
    ).fetchone()[0]
    stats = build_ecse_score_distributions(conn, dry_run=args.dry_run, rebuild=args.rebuild)
    fixtures_after = conn.execute(
        "SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_score_distributions"
    ).fetchone()[0]
    audit = audit_ecse_score_distributions(conn)

    summary = {
        "phase": "ECSE-1D",
        "method_version": METHOD_VERSION,
        "dry_run": args.dry_run,
        "rebuild": args.rebuild,
        "fixtures_before": fixtures_before,
        "fixtures_after": fixtures_after,
        "build": stats.to_dict(),
        "audit": audit,
        "top5_sample": sample_top_n_summary(conn, sample_fixtures=3, top_n=5) if fixtures_after else [],
        "top10_sample": sample_top_n_summary(conn, sample_fixtures=3, top_n=10) if fixtures_after else [],
        "fingerprint": distribution_fingerprint(conn) if fixtures_after and not args.dry_run else None,
    }

    if not args.dry_run:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"\necse_score_distributions fixtures: {fixtures_after}")
    if not args.dry_run:
        print(f"Summary: {SUMMARY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
