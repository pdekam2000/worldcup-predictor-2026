#!/usr/bin/env python3
"""Unified A+B forward evaluation automation cycle (timers disabled externally)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.automation import AUTOMATION_ENABLED, automation_status
from worldcup_predictor.forward_evaluation.orchestrator import run_forward_evaluation_automation_cycle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run unified forward evaluation automation cycle")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default today)")
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-lock", action="store_true")
    args = parser.parse_args()

    if AUTOMATION_ENABLED:
        print(json.dumps({"warning": "AUTOMATION_ENABLED is True but timers must remain disabled in this phase"}))

    try:
        result = run_forward_evaluation_automation_cycle(
            target_date=args.date,
            timezone=args.timezone,
            dry_run=args.dry_run,
            skip_lock=args.skip_lock,
        )
    except RuntimeError as exc:
        if str(exc).startswith("lock_active"):
            print(json.dumps({"success": False, "error": str(exc), "automation": automation_status()}, indent=2))
            return 2
        raise

    result["automation"] = automation_status()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
