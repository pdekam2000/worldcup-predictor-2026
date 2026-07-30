#!/usr/bin/env python3
"""Phase 3 staged runner: missing-result recovery, evaluation, slices, detector."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.infra_l2f_forward.deep_slices import run_deep_slice_report
from worldcup_predictor.research.infra_l2f_forward.high_goal_detector import evaluate_detector
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    COHORT_HISTORICAL,
    aggregate_eval_metrics,
)
from worldcup_predictor.research.infra_l2f_forward.result_recovery import (
    COHORT_RECOVERED,
    df_line,
    inventory_missing_result_freezes,
    run_result_recovery_batch,
    summarize_inventory,
    write_inventory,
)
from worldcup_predictor.research.infra_l2f_forward.true_forward_report import true_forward_summary


def _freeze_hash(eval_conn: sqlite3.Connection) -> tuple[str, int]:
    rows = eval_conn.execute(
        "SELECT prediction_id, fixture_id, frozen_at, lambda_home, lambda_away, freeze_status "
        "FROM frozen_predictions ORDER BY prediction_id"
    ).fetchall()
    return hashlib.sha256(repr([tuple(r) for r in rows]).encode()).hexdigest(), len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-db", default="data/evaluation/forward_prediction_tracking.db")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--stage", choices=("inventory", "recover", "report"), default="inventory")
    ap.add_argument("--batch-size", type=int, default=15)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-provider", action="store_true")
    ap.add_argument("--min-free-gb", type=float, default=8.0)
    ap.add_argument("--resume-after", type=int, default=None)
    ap.add_argument("--out-dir", default="artifacts/l2f_phase3")
    args = ap.parse_args()
    dry_run = not args.apply
    if args.dry_run:
        dry_run = True

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    disk_before = df_line()
    (out_dir / "disk_before.txt").write_text(disk_before + "\n", encoding="utf-8")

    eval_conn = sqlite3.connect(args.eval_db)
    eval_conn.row_factory = sqlite3.Row
    fi_conn = sqlite3.connect(args.fi_db)
    fi_conn.row_factory = sqlite3.Row
    prod_conn = sqlite3.connect(args.fi_db)
    prod_conn.row_factory = sqlite3.Row

    freeze_hash, freeze_n = _freeze_hash(eval_conn)
    missing = inventory_missing_result_freezes(eval_conn)
    inv = summarize_inventory(missing)
    write_inventory(missing, out_dir / "missing_result_inventory.json")
    (out_dir / "missing_result_inventory.md").write_text(
        "# Missing-result inventory\n\n```json\n" + json.dumps(inv, indent=2) + "\n```\n",
        encoding="utf-8",
    )

    result: dict = {
        "stage": args.stage,
        "disk_before": disk_before,
        "freeze_hash_before": freeze_hash,
        "freeze_n": freeze_n,
        "inventory": inv,
        "dry_run": dry_run,
    }

    if args.stage == "recover":
        batch = run_result_recovery_batch(
            eval_conn=eval_conn,
            prod_conn=prod_conn,
            fi_conn=fi_conn,
            batch_size=args.batch_size,
            dry_run=dry_run,
            allow_provider=not args.no_provider,
            min_free_gb=args.min_free_gb,
            disk_line=disk_before,
            resume_after_fixture_id=args.resume_after,
            generate_missing_shadow=True,
        )
        disk_after = df_line()
        batch.disk_after = disk_after
        (out_dir / "disk_after.txt").write_text(disk_after + "\n", encoding="utf-8")
        freeze_hash_after, _ = _freeze_hash(eval_conn)
        result["batch"] = {
            "processed": batch.processed,
            "recovered_db": batch.recovered_db,
            "recovered_provider": batch.recovered_provider,
            "already_present": batch.already_present,
            "not_finished": batch.not_finished,
            "postponed_or_cancelled": batch.postponed_or_cancelled,
            "provider_unavailable": batch.provider_unavailable,
            "ambiguous": batch.ambiguous,
            "conflicting": batch.conflicting,
            "unresolved": batch.unresolved,
            "evaluated": batch.evaluated,
            "shadow_generated": batch.shadow_generated,
            "fixture_ids": batch.fixture_ids,
            "stopped_reason": batch.stopped_reason,
            "details": batch.details,
            "disk_after": disk_after,
        }
        result["freeze_hash_after"] = freeze_hash_after
        result["freeze_unchanged"] = freeze_hash_after == freeze_hash
        if freeze_hash_after != freeze_hash:
            result["stopped"] = "canonical_freeze_hash_changed"

    if args.stage in ("recover", "report"):
        result["metrics_historical"] = aggregate_eval_metrics(fi_conn, cohort_type=COHORT_HISTORICAL)
        result["metrics_recovered"] = aggregate_eval_metrics(fi_conn, cohort_type=COHORT_RECOVERED)
        result["true_forward"] = true_forward_summary(fi_conn, eval_conn)
        result["deep_slices"] = run_deep_slice_report(eval_conn, fi_conn)
        result["high_goal_detector"] = evaluate_detector(
            eval_conn,
            fi_conn,
            out_path=out_dir / "high_goal_detector_research.json",
        )

    out_path = out_dir / "phase3_stage_result.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "stage": args.stage, "missing": inv["total_missing_result_freezes"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
