#!/usr/bin/env python3
"""TOP10-TO-TOP3-SELECTOR-1 — Shadow selector backtest (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.top10_to_top3_selector.runner import run_selector_backtest

PHASE = "TOP10-TO-TOP3-SELECTOR-1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Top10→Top3 selector shadow backtest")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"))
    args = parser.parse_args()

    print(f"{PHASE} shadow backtest (read-only)\n")
    result = run_selector_backtest(db_path=args.db_path, artifacts_dir=args.artifacts_dir)
    p = result["payload"]
    print(
        json.dumps(
            {
                "phase": PHASE,
                "finished_count": p["finished_count"],
                "raw_top3_pct": p["summary"]["raw_top3_hit_rate_pct"],
                "top10_coverage_pct": p["summary"]["top10_coverage_pct"],
                "best_strategy": p["summary"]["best_strategy_id"],
                "best_top3_pct": p["summary"]["best_top3_hit_rate_pct"],
                "best_delta_pp": p["summary"]["best_delta_vs_raw_pp"],
                "promotion_gate": p["promotion_gate"]["status"],
                "feature_path": result["feature_path"],
                "json_path": result["json_path"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
