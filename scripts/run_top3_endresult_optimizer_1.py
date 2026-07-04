#!/usr/bin/env python3
"""TOP3-ENDRESULT-OPTIMIZER-1 — Shadow Top3 portfolio backtest (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.top3_endresult_optimizer.runner import run_optimizer_backtest

PHASE = "TOP3-ENDRESULT-OPTIMIZER-1"


def main() -> int:
    parser = argparse.ArgumentParser(description="TOP3 End Result optimizer shadow backtest")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"))
    args = parser.parse_args()

    print(f"{PHASE} shadow backtest (read-only)\n")
    result = run_optimizer_backtest(db_path=args.db_path, artifacts_dir=args.artifacts_dir)
    p = result["payload"]
    best = p["best_strategy_id"]
    best_rate = p["strategy_summary"][best]["segments"]["all"].get("top3_hit_rate_pct")
    baseline_rate = p["baseline_audit"]["raw_top3_hit_rate_pct"]

    print(
        json.dumps(
            {
                "phase": PHASE,
                "finished_count": p["finished_count"],
                "baseline_top3_hit_pct": baseline_rate,
                "best_strategy": best,
                "best_top3_hit_pct": best_rate,
                "json_path": result["json_path"],
                "csv_path": result["csv_path"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
