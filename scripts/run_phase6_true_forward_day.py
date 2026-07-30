#!/usr/bin/env python3
"""Phase 6 — high-volume true-forward day runner (staged caps).

Stages:
  1) --dry-run          discovery/sampling only (no prediction writes)
  2) --cap 20           pilot
  3) --cap 50           after validation
  4) --cap 100          only after prior stages pass

No promotion. No routing activation. No historical relabel as true_forward.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("APP_ENV", "production")


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.db import connect_eval_db
    from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
    from worldcup_predictor.research.infra_l2f_forward.diversity_sampling import DEFAULT_SEED
    from worldcup_predictor.research.infra_l2f_forward.hv_batch import (
        promotion_gate_for_next_stage,
        run_hv_true_forward_day,
    )
    from worldcup_predictor.research.infra_l2f_forward.phase6_reports import (
        build_cumulative_report,
        build_daily_report,
        write_report,
    )

    parser = argparse.ArgumentParser(description="Phase 6 HV true-forward day")
    parser.add_argument("--date", default=None, help="Vienna YYYY-MM-DD (default: tomorrow)")
    parser.add_argument("--cap", type=int, default=20, help="Daily selected fixture cap")
    parser.add_argument("--dry-run", action="store_true", help="Stage 1: no prediction writes")
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--resume-checkpoint", default=None)
    parser.add_argument("--min-free-gb", type=float, default=8.0)
    parser.add_argument("--artifact-root", default=None)
    args = parser.parse_args(argv)

    tz = ZoneInfo("Europe/Vienna")
    if args.date:
        vienna_date = args.date
    else:
        # Default tomorrow for true-forward collection
        from datetime import timedelta

        vienna_date = (datetime.now(tz).date() + timedelta(days=1)).isoformat()

    bootstrap_gpt_actions_runtime()
    settings = get_settings()
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db()
    fi = prod  # jobs/checkpoints live on FI DB

    art_root = Path(args.artifact_root) if args.artifact_root else (
        ROOT / "artifacts" / "phase6_hv_tf" / vienna_date
    )

    result = run_hv_true_forward_day(
        vienna_date=vienna_date,
        daily_cap=int(args.cap),
        dry_run=bool(args.dry_run),
        seed=str(args.seed),
        prod_conn=prod,
        eval_conn=eval_conn,
        fi_conn=fi,
        settings=settings,
        artifact_root=art_root,
        min_free_gb=float(args.min_free_gb),
        resume_checkpoint_id=args.resume_checkpoint,
    )

    daily = build_daily_report(vienna_date=vienna_date, batch_result=result.to_dict())
    cum = build_cumulative_report(fi_conn=fi, eval_conn=eval_conn)
    write_report(Path(result.artifact_dir) / "daily_report.json", daily)
    write_report(Path(result.artifact_dir) / "cumulative_report.json", cum)

    gate = promotion_gate_for_next_stage(
        canonical_success=result.canonical_success,
        canonical_attempted=max(1, result.canonical_success + result.canonical_blocked + result.canonical_failed)
        if not result.dry_run
        else 0,
        shadow_success=result.shadow_success,
        shadow_attempted=max(1, result.shadow_success + result.shadow_failed + result.shadow_skipped)
        if not result.dry_run
        else 0,
    )

    summary = {
        "git_sha": _git_sha(),
        "vienna_date": vienna_date,
        "stage": result.stage,
        "dry_run": result.dry_run,
        "cap": result.daily_cap,
        "discovered": result.discovered,
        "eligible": result.eligible,
        "selected": result.selected,
        "processed": result.processed,
        "canonical_success": result.canonical_success,
        "shadow_success": result.shadow_success,
        "stopped_reason": result.stopped_reason,
        "checkpoint_id": result.checkpoint_id,
        "artifact_dir": result.artifact_dir,
        "next_stage_gate": gate,
        "explicit": "No promotion and no routing activation occurred.",
    }
    write_report(Path(result.artifact_dir) / "run_summary.json", summary)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if not result.stopped_reason or "disk" not in str(result.stopped_reason) else 3


if __name__ == "__main__":
    raise SystemExit(main())
