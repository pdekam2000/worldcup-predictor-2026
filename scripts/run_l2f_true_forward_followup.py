#!/usr/bin/env python3
"""Bounded true-forward result follow-up runner (cron/systemd compatible)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if (ROOT / ".env.production").exists() and not os.environ.get("APP_ENV"):
    os.environ["APP_ENV"] = "production"

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.infra_l2f_forward.true_forward_followup import run_true_forward_followup_batch


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-db", default="data/evaluation/forward_prediction_tracking.db")
    ap.add_argument("--fi-db", default="data/football_intelligence.db")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--grace-hours", type=float, default=2.5)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-free-gb", type=float, default=8.0)
    ap.add_argument("--out-dir", default="artifacts/l2f_true_forward_followup")
    args = ap.parse_args()
    dry = not args.apply
    if args.dry_run:
        dry = True
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    eval_conn = sqlite3.connect(args.eval_db)
    eval_conn.row_factory = sqlite3.Row
    fi = sqlite3.connect(args.fi_db)
    fi.row_factory = sqlite3.Row
    prod = sqlite3.connect(args.fi_db)
    prod.row_factory = sqlite3.Row
    batch = run_true_forward_followup_batch(
        eval_conn=eval_conn,
        prod_conn=prod,
        fi_conn=fi,
        batch_size=args.batch_size,
        dry_run=dry,
        grace_hours=args.grace_hours,
        min_free_gb=args.min_free_gb,
        settings=settings,
    )
    payload = {
        "dry_run": batch.dry_run,
        "processed": batch.processed,
        "by_class": batch.by_class,
        "evaluated": batch.evaluated,
        "fixture_ids": batch.fixture_ids,
        "details": batch.details,
        "stopped_reason": batch.stopped_reason,
        "disk_before": batch.disk_before,
        "disk_after": batch.disk_after,
    }
    path = out_dir / "followup_result.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"out": str(path), "processed": batch.processed, "by_class": batch.by_class}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
