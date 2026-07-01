#!/usr/bin/env python3
"""Dry-run preview: promote OddAlerts CSV policy probabilities to odds_snapshots."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import PROCESS_DATE
from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import (
    REPORT_PATH,
    artifact_paths,
    build_report_markdown,
    promotion_final_recommendation,
    run_promotion_dryrun,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview OddAlerts CSV promotion to odds_snapshots (dry-run only)"
    )
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--sample-limit", type=int, default=10)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    paths = artifact_paths(args.date)
    missing = [k for k, p in paths.items() if k in ("matrix", "ecse_readiness", "policy_preview") and not p.exists()]
    if missing:
        for k in missing:
            print(f"Missing required artifact: {paths[k]}", file=sys.stderr)
        return 2

    conn = connect(get_settings().sqlite_path)
    odds_before = int(conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"])
    result = run_promotion_dryrun(
        conn,
        process_date=args.date,
        sample_limit=args.sample_limit,
    )
    odds_after = int(conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"])
    conn.close()

    result["final_recommendation"] = promotion_final_recommendation(result)
    result["odds_snapshots_before"] = odds_before
    result["odds_snapshots_after"] = odds_after
    result["odds_snapshots_written"] = odds_after - odds_before

    out_path = paths["dryrun_out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    REPORT_PATH.write_text(build_report_markdown(result), encoding="utf-8")

    summary = {
        k: result[k]
        for k in (
            "phase",
            "ready_full_fixture_count",
            "candidate_count",
            "would_insert_count",
            "would_enrich_count",
            "skipped_existing_fresh_count",
            "conflict_review_count",
            "final_recommendation",
            "odds_snapshots_written",
        )
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Written: {out_path}")
    print(f"Written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
