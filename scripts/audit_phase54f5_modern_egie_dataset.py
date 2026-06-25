#!/usr/bin/env python3
"""Phase 54F-5 — audit modern EGIE dataset coverage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f5_modern_egie_dataset"


def main() -> int:
    import pandas as pd

    summary_path = ARTIFACT_DIR / "modern_egie_dataset_summary.json"
    parquet_path = ARTIFACT_DIR / "modern_egie_dataset.parquet"
    if not summary_path.is_file():
        from worldcup_predictor.egie.xg_backtest.modern_dataset_builder import ModernEgieDatasetBuilder

        ModernEgieDatasetBuilder().save(ARTIFACT_DIR)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    df = pd.read_parquet(parquet_path) if parquet_path.is_file() else pd.DataFrame()

    test_n = 0
    if len(df) >= 30:
        ordered = df.sort_values("kickoff_utc")
        split_at = max(1, len(ordered) - max(10, len(ordered) // 3))
        test_n = len(ordered.iloc[split_at:])

    report = {
        "phase": "54F-5",
        "total_candidate_fixtures": summary.get("candidate_fixtures", 0),
        "usable_fixtures": summary.get("usable_fixtures", 0),
        "unusable_fixtures": summary.get("unusable_fixtures", 0),
        "rolling_xg_coverage_pct": summary.get("rolling_xg_coverage_pct", 0),
        "by_league": summary.get("by_league", {}),
        "by_season": summary.get("by_season", {}),
        "first_goal_target_coverage": summary.get("first_goal_team_labeled", 0),
        "goal_range_target_coverage": summary.get("goal_range_labeled", 0),
        "team_goals_target_coverage": summary.get("team_goals_labeled", 0),
        "leakage_safe_count": summary.get("leakage_safe_count", 0),
        "threshold_30_met": bool(summary.get("threshold_30_met")),
        "threshold_50_preferred": bool(summary.get("threshold_50_preferred")),
        "estimated_test_fixtures": test_n,
        "ab_ready": bool(summary.get("threshold_30_met")) and test_n >= 10,
    }

    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["threshold_30_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
