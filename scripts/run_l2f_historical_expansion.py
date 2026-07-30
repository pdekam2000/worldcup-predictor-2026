#!/usr/bin/env python3
"""Stage runner for L2-F historical expansion (dry-run / bounded batches)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.infra_l2f_forward.historical_cohort import (
    CLASS_ELIGIBLE_HISTORICAL,
    inventory_eval_db,
    summarize,
    write_inventory_csv,
    write_inventory_report,
)
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    COHORT_HISTORICAL,
    aggregate_eval_metrics,
    run_historical_replay_batch,
)
from worldcup_predictor.research.infra_l2f_forward.leakage_checks import (
    assert_prediction_before_kickoff,
    check_shadow_payloads_no_results,
)


def _df_line() -> str:
    try:
        out = subprocess.check_output(["df", "-h", "/"], text=True)
        return out.strip().splitlines()[-1]
    except Exception:
        return "N/A"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-db", default="data/evaluation/forward_prediction_tracking.db")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--stage", choices=("inventory", "batch"), default="inventory")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--apply", action="store_true", help="Actually write shadow rows")
    ap.add_argument("--min-free-gb", type=float, default=8.0)
    ap.add_argument("--out-dir", default="artifacts/l2f_historical_expansion")
    ap.add_argument("--resume-after", type=int, default=None)
    args = ap.parse_args()
    dry_run = not args.apply
    if args.dry_run:
        dry_run = True

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    disk_before = _df_line()
    (out_dir / "disk_before.txt").write_text(disk_before + "\n", encoding="utf-8")

    eval_conn = sqlite3.connect(args.eval_db)
    eval_conn.row_factory = sqlite3.Row
    candidates = inventory_eval_db(eval_conn)
    summary = summarize(candidates)
    write_inventory_csv(candidates, out_dir / "historical_fixture_eligibility.csv")
    write_inventory_report(summary, out_dir / "historical_expansion_audit.json")
    (out_dir / "historical_expansion_audit.md").write_text(
        "# Historical expansion audit\n\n```json\n"
        + json.dumps(summary, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )

    result: dict = {"stage": args.stage, "summary": summary, "disk_before": disk_before}

    if args.stage == "batch":
        fi_conn = sqlite3.connect(args.fi_db)
        fi_conn.row_factory = sqlite3.Row

        def integrity(c, meta):
            leak = assert_prediction_before_kickoff(c.frozen_at, c.kickoff)
            if leak:
                return leak
            if meta.get("status") == "success":
                issues = check_shadow_payloads_no_results(fi_conn, c.fixture_id)
                if issues:
                    return issues[0]
            return None

        batch = run_historical_replay_batch(
            eval_conn=eval_conn,
            fi_conn=fi_conn,
            batch_size=args.batch_size,
            dry_run=dry_run,
            cohort=COHORT_HISTORICAL,
            min_free_gb=args.min_free_gb,
            disk_line=disk_before,
            resume_after_fixture_id=args.resume_after,
            integrity_hooks=[integrity],
        )
        disk_after = _df_line()
        batch.disk_after = disk_after
        (out_dir / "disk_after.txt").write_text(disk_after + "\n", encoding="utf-8")
        metrics = aggregate_eval_metrics(fi_conn, cohort_type=COHORT_HISTORICAL)
        result["batch"] = {
            "dry_run": batch.dry_run,
            "processed": batch.processed,
            "success": batch.success,
            "skipped": batch.skipped,
            "blocked": batch.blocked,
            "failed": batch.failed,
            "fixture_ids": batch.fixture_ids,
            "stopped_reason": batch.stopped_reason,
            "details": batch.details,
            "disk_after": disk_after,
            "metrics": metrics,
        }
        fi_conn.close()

    eval_conn.close()
    (out_dir / "phase2_stage_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "eligible_historical": summary.get("eligible_historical_replay"), "stage": args.stage}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
