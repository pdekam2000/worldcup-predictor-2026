#!/usr/bin/env python3
"""Phase 46C-2 post-deploy: re-evaluate stored predictions with advanced markets."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.automation.worldcup_background.result_evaluation_job import (
        run_evaluate_worldcup_results,
    )
    from worldcup_predictor.config.settings import get_settings

    settings = get_settings()
    result = run_evaluate_worldcup_results(
        settings=settings,
        skip_unchanged=False,
        rebuild_summary=True,
    )
    print("Phase 46C-2 post-deploy re-evaluation")
    print(f"  Scanned: {result.scanned}")
    print(f"  Evaluated: {result.evaluated}")
    print(f"  Updated: {result.updated}")
    print(f"  Skipped unchanged: {result.skipped_unchanged}")
    print(f"  Errors: {result.errors}")
    return 0 if result.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
