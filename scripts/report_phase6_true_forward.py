#!/usr/bin/env python3
"""Emit Phase 6 cumulative / readiness report JSON."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "production")


def main(argv: list[str] | None = None) -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.db import connect_eval_db
    from worldcup_predictor.research.infra_l2f_forward.phase6_reports import (
        build_cumulative_report,
        write_report,
    )
    from worldcup_predictor.research.infra_l2f_forward.true_forward_followup import (
        run_true_forward_followup_batch,
    )

    p = argparse.ArgumentParser()
    p.add_argument("--out", default="artifacts/phase6_hv_tf/cumulative_latest.json")
    p.add_argument("--followup", action="store_true")
    p.add_argument("--followup-dry-run", action="store_true")
    p.add_argument("--followup-batch-size", type=int, default=50)
    args = p.parse_args(argv)

    settings = get_settings()
    fi = connect(settings.sqlite_path)
    ev = connect_eval_db()
    followup = None
    if args.followup or args.followup_dry_run:
        followup = run_true_forward_followup_batch(
            eval_conn=ev,
            prod_conn=fi,
            fi_conn=fi,
            batch_size=int(args.followup_batch_size),
            dry_run=bool(args.followup_dry_run) or not args.followup,
            settings=settings,
        )
    report = build_cumulative_report(fi_conn=fi, eval_conn=ev)
    if followup is not None:
        report["followup"] = {
            "dry_run": followup.dry_run,
            "processed": followup.processed,
            "by_class": followup.by_class,
            "evaluated": followup.evaluated,
            "stopped_reason": followup.stopped_reason,
        }
    path = write_report(Path(args.out), report)
    print(json.dumps({"wrote": str(path), "evaluated": report.get("total_evaluated"), "explicit": report.get("explicit")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
