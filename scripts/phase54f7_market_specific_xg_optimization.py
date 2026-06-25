#!/usr/bin/env python3
"""Phase 54F-7 — market-specific xG optimization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = ROOT / "artifacts" / "phase54f6_expanded_dataset" / "expanded_egie_dataset.parquet"


def main() -> int:
    from worldcup_predictor.egie.xg_backtest.market_specific_optimizer import MarketSpecificXgOptimizer

    if not DATASET.is_file():
        print(json.dumps({"error": f"dataset_missing:{DATASET}"}))
        return 1

    result = MarketSpecificXgOptimizer(DATASET).save()
    print(json.dumps(
        {
            "final_recommendation": result["final_recommendation"],
            "production_readiness": result["production_readiness"],
            "first_goal_team": result["markets"]["first_goal_team"]["recommendation"],
            "goal_range_best_arm": result["markets"]["goal_range"]["best_arm"],
            "team_goals_best_arm": result["markets"]["team_goals"]["best_arm"],
            "xg_lite_vs_full": result["xg_lite_vs_full"]["lite_outperforms_full_markets"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
