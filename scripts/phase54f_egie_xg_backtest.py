#!/usr/bin/env python3
"""Phase 54F — EGIE xG backtest arm (backtest only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f_egie_xg_backtest"
MODERN_ARTIFACT_DIR = ROOT / "artifacts" / "phase54f5_modern_egie_dataset"


def main() -> int:
    import pandas as pd

    from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import EgieXgDatasetBuilder
    from worldcup_predictor.egie.xg_backtest.xg_backtest_runner import XgBacktestRunner
    from worldcup_predictor.egie.xg_backtest.xg_leakage_audit import run_xg_leakage_audit

    parser = argparse.ArgumentParser(description="Phase 54F EGIE xG A/B backtest")
    parser.add_argument(
        "--dataset",
        type=str,
        default="",
        help="Path to modern EGIE parquet (Phase 54F-5); default uses legacy UEFA cache dataset",
    )
    args = parser.parse_args()

    out_dir = MODERN_ARTIFACT_DIR if args.dataset else ARTIFACT_DIR
    if args.dataset and "phase54f6" in args.dataset.replace("\\", "/"):
        out_dir = ROOT / "artifacts" / "phase54f6_expanded_dataset"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.is_file():
            print(json.dumps({"error": f"dataset_not_found:{dataset_path}"}))
            return 1
        df = pd.read_parquet(dataset_path)
        coverage = {
            "fixtures_total": len(df),
            "fixtures_with_xg": int(df["xg_available"].sum()) if "xg_available" in df.columns else 0,
            "xg_coverage_pct": round(100 * float(df["xg_available"].mean()), 2) if len(df) else 0.0,
            "dataset_path": str(dataset_path),
            "phase": "54F-5-modern",
        }
        (out_dir / "dataset_coverage.json").write_text(json.dumps({"coverage": coverage}, indent=2), encoding="utf-8")
        print(json.dumps(coverage, indent=2))
    else:
        print("Building datasets...")
        meta = EgieXgDatasetBuilder().save(ARTIFACT_DIR)
        coverage = meta.get("coverage", {})
        print(json.dumps(coverage, indent=2))
        df = None

    print("Running leakage audit...")
    leakage = run_xg_leakage_audit()
    print(f"Leakage audit: {leakage.get('status')}")

    print("Running A/B backtest...")
    runner = XgBacktestRunner()
    result = runner.run(df=df)
    if args.dataset:
        result["phase"] = "54F-5-modern" if "phase54f5" in str(args.dataset) else "54F-6-expanded"
        result["dataset_path"] = args.dataset
        (out_dir / "ab_test_results.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    recommendation = XgBacktestRunner.recommend_value(result)
    result["recommendation"] = recommendation
    summary_path = out_dir / "phase54f_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "coverage": result.get("coverage"),
                "recommendation": recommendation,
                "markets": {
                    k: {
                        "arm_a": (v.get("arm_a_baseline") or {}).get("accuracy"),
                        "arm_b": (v.get("arm_b_xg") or {}).get("accuracy"),
                        "delta_accuracy": (v.get("delta") or {}).get("accuracy"),
                    }
                    for k, v in (result.get("markets") or {}).items()
                },
                "leakage_audit": leakage.get("status"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(result.get("markets", {}), indent=2, default=str))
    print(f"Recommendation: {recommendation}")

    if args.dataset and out_dir.name == "phase54f6_expanded_dataset":
        from worldcup_predictor.egie.xg_backtest.xg_feature_importance import save_feature_analysis

        fi = save_feature_analysis(out_dir / "ab_test_results.json", out_dir)
        (out_dir / "feature_importance_analysis.json").write_text(json.dumps(fi, indent=2), encoding="utf-8")
        print("Feature importance analysis saved.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
