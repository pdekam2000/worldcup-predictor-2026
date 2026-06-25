#!/usr/bin/env python3
"""Phase 54F-5 — build modern EGIE xG backtest dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.xg_backtest.modern_dataset_builder import ModernEgieDatasetBuilder

    summary = ModernEgieDatasetBuilder().save()
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary.get("usable_fixtures", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
