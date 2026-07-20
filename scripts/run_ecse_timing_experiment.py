#!/usr/bin/env python3
"""Capture EARLY / MID / LATE research snapshots for the ECSE timing experiment.

Does not overwrite canonical freezes. Restores WSP/ECSE after temporary runs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.research.ecse_timing_experiment.capture import run_timing_capture
from worldcup_predictor.research.ecse_timing_experiment.constants import ARTIFACT_ROOT, TZ_NAME
from worldcup_predictor.research.ecse_timing_experiment.report_builder import build_early_report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ECSE timing experiment snapshot capture (research only)")
    p.add_argument("--date", required=True, help="YYYY-MM-DD or tomorrow/today (Europe/Vienna)")
    p.add_argument("--snapshot", required=True, choices=["early", "mid", "late", "EARLY", "MID", "LATE"])
    p.add_argument("--scope", default="owner", choices=["owner"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    args = p.parse_args(argv)

    target = resolve_target_date(args.date, TZ_NAME).isoformat()
    summary = run_timing_capture(
        experiment_date=target,
        snapshot_class=args.snapshot.upper(),
        scope=args.scope,
        dry_run=args.dry_run,
        root=ROOT,
    )

    # EARLY report
    if args.snapshot.upper() == "EARLY" and not args.dry_run:
        art = ROOT / ARTIFACT_ROOT / target / "early"
        discovery = {}
        results = []
        integrity = summary.get("integrity") or {}
        disc_path = art / "discovery.json"
        res_path = art / "capture_results.json"
        integ_path = art / "integrity.json"
        if disc_path.is_file():
            discovery = json.loads(disc_path.read_text(encoding="utf-8"))
        if res_path.is_file():
            results = (json.loads(res_path.read_text(encoding="utf-8")) or {}).get("results") or []
        if integ_path.is_file():
            integrity = json.loads(integ_path.read_text(encoding="utf-8"))
        report = build_early_report(
            root=ROOT,
            experiment_date=target,
            summary=summary,
            discovery=discovery,
            results=results,
            integrity=integrity,
        )
        summary["report_path"] = str(report)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    else:
        print(summary.get("final_status"))
        print(f"experiment_id={summary.get('experiment_id')}")
        print(f"captured={summary.get('captured')} blocked={summary.get('blocked')} idempotent={summary.get('idempotent')}")
        if summary.get("report_path"):
            print(f"report={summary['report_path']}")
        print(f"MID: {summary.get('mid_command')}")
        print(f"LATE: {summary.get('late_command')}")
        print(f"EVAL: {summary.get('evaluate_command')}")
    return 0 if str(summary.get("final_status") or "").startswith("ECSE_TIMING_EXPERIMENT_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
