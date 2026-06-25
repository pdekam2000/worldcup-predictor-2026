#!/usr/bin/env python3
"""Phase 46C-1 post-deploy: backfill outcome detail for stored predictions."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.automation.worldcup_background.result_refresh import (
        backfill_stored_prediction_outcomes,
    )

    result = backfill_stored_prediction_outcomes(force=True)
    print("Phase 46C-1 post-deploy outcome sync")
    print(f"  Scanned: {result.scanned}")
    print(f"  API fixture fetches: {result.api_fetches}")
    print(f"  API event fetches: {result.api_event_fetches}")
    print(f"  Results updated: {result.results_updated}")
    print(f"  Outcomes persisted: {result.outcomes_persisted}")
    print(f"  Outcome sync skipped (complete): {result.outcomes_skipped_complete}")
    print(f"  Errors: {result.errors}")
    return 0 if result.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
