#!/usr/bin/env python3
"""Phase 46B post-deploy: run legacy import on production archive."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.automation.worldcup_background.legacy_prediction_import import (
        run_legacy_prediction_import,
    )

    result = run_legacy_prediction_import(dry_run=False)
    print("Phase 46B post-deploy legacy import")
    print(f"  Archive before: {result.archive_total_before}")
    print(f"  Archive after:  {result.archive_total_after}")
    print(f"  Imported:       {result.imported}")
    print(f"  Quarantined:    {result.quarantined}")
    print(f"  Duplicates skipped: {result.duplicates_skipped}")
    print(f"  Errors:         {len(result.errors)}")
    for err in result.errors[:20]:
        print(f"    - {err}")
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
