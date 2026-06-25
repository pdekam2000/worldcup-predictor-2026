#!/usr/bin/env python3
"""Phase 54F-6 — build expanded modern EGIE dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.xg_backtest.expanded_dataset_builder import ExpandedEgieDatasetBuilder

    summary = ExpandedEgieDatasetBuilder().save()
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("usable_fixtures", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
