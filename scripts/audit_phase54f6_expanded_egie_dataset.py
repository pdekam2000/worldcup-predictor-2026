#!/usr/bin/env python3
"""Phase 54F-6 — expanded dataset coverage audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f6_expanded_dataset"


def main() -> int:
    import pandas as pd

    summary_path = ARTIFACT_DIR / "expanded_egie_dataset_summary.json"
    parquet_path = ARTIFACT_DIR / "expanded_egie_dataset.parquet"
    if not summary_path.is_file():
        from worldcup_predictor.egie.xg_backtest.expanded_dataset_builder import ExpandedEgieDatasetBuilder

        ExpandedEgieDatasetBuilder().save(ARTIFACT_DIR)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    df = pd.read_parquet(parquet_path) if parquet_path.is_file() else pd.DataFrame()

    test_n = 0
    if len(df) >= 30:
        ordered = df.sort_values("kickoff_utc")
        split_at = max(1, len(ordered) - max(10, len(ordered) // 3))
        test_n = len(ordered.iloc[split_at:])

    report = {
        "phase": "54F-6",
        "fixtures_scanned": summary.get("fixtures_scanned", 0),
        "fixtures_usable": summary.get("usable_fixtures", 0),
        "fixtures_unusable": summary.get("unusable_fixtures", 0),
        "coverage_pct": summary.get("rolling_xg_coverage_pct", 0),
        "usable_by_league": summary.get("by_league", {}),
        "usable_by_season": summary.get("by_season", {}),
        "rolling_xg_3_coverage": summary.get("rolling_xg_3_coverage", 0),
        "rolling_xg_5_coverage": summary.get("rolling_xg_5_coverage", 0),
        "rolling_xg_10_coverage": summary.get("rolling_xg_10_coverage", 0),
        "rolling_xg_3_pct": summary.get("rolling_xg_3_pct", 0),
        "rolling_xg_5_pct": summary.get("rolling_xg_5_pct", 0),
        "rolling_xg_10_pct": summary.get("rolling_xg_10_pct", 0),
        "first_goal_target_coverage": summary.get("first_goal_team_labeled", 0),
        "goal_range_target_coverage": summary.get("goal_range_labeled", 0),
        "team_goals_target_coverage": summary.get("team_goals_labeled", 0),
        "leakage_safe_count": summary.get("leakage_safe_count", 0),
        "threshold_300_met": bool(summary.get("threshold_300_met")),
        "threshold_500_preferred": bool(summary.get("threshold_500_preferred")),
        "estimated_test_fixtures": test_n,
        "ab_ready": bool(summary.get("threshold_300_met")),
    }
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["threshold_300_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
