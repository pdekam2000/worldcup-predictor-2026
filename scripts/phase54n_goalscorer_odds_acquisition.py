#!/usr/bin/env python3
"""Phase 54N — Goalscorer odds acquisition & expansion (research only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_odds_acquisition.runner import run_phase54n

    report = run_phase54n()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "api_football_gs": (report.get("candidate_counts") or {}).get("api_football_with_gs"),
                "sportmonks_gs": (report.get("candidate_counts") or {}).get("sportmonks_with_gs"),
                "reach_50_plan_a": (report.get("backfill") or {}).get("reach_50_with_plan_a"),
                "market_split_total": (report.get("market_split") or {}).get("total_rows"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
