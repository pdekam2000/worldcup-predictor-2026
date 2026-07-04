#!/usr/bin/env python3
"""TOP10-COVERAGE-1 — End Result candidate coverage analysis (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.top10_coverage.runner import run_coverage_analysis

PHASE = "TOP10-COVERAGE-1"


def main() -> int:
    parser = argparse.ArgumentParser(description="TOP10 coverage analysis")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--artifacts-dir", default=str(ROOT / "artifacts"))
    args = parser.parse_args()

    print(f"{PHASE} read-only analysis\n")
    result = run_coverage_analysis(db_path=args.db_path, artifacts_dir=args.artifacts_dir)
    s = result["payload"]["summary"]
    print(
        json.dumps(
            {
                "phase": PHASE,
                "finished_count": s.get("finished_matches"),
                "top5_coverage_pct": s.get("top5_coverage_pct"),
                "top10_coverage_pct": s.get("top10_coverage_pct"),
                "top20_coverage_pct": s.get("top20_coverage_pct"),
                "full_coverage_pct": s.get("full_distribution_coverage_pct"),
                "top5_misses": len(result["payload"]["top5_miss_diagnoses"]),
                "json_path": result["json_path"],
                "csv_path": result["csv_path"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
