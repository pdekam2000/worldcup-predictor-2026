#!/usr/bin/env python3
"""Hotfix Pack 2 — re-evaluate finished fixtures with stored predictions."""

from __future__ import annotations

import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

from worldcup_predictor.automation.worldcup_background.result_evaluation_job import run_evaluate_worldcup_results


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    result = run_evaluate_worldcup_results(limit=limit, skip_unchanged=False, mode="stored_first")
    print(
        {
            "scanned": result.scanned,
            "evaluated": result.evaluated,
            "updated": result.updated,
            "skipped": result.skipped,
            "errors": result.errors,
        }
    )
    return 0 if result.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
