#!/usr/bin/env python3
"""Phase 54O — API-Football goalscorer odds bridge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_bridge.runner import run_phase54o

    report = run_phase54o()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "mapped_fixtures": (report.get("fixture_bridge") or {}).get("mapped"),
                "mapping_rate": (report.get("player_mapping") or {}).get("mapping_rate"),
                "dataset_v2_rows": (report.get("dataset_v2") or {}).get("rows"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
