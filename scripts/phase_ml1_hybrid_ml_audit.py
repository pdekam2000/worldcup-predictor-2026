#!/usr/bin/env python3
"""PHASE ML-1 — Hybrid ML + Market Intelligence Foundation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    from worldcup_predictor.egie.ml1.dataset_builder import (
        build_dataset_inventory,
        build_unified_dataset,
        build_uefa_evaluation_rows,
    )
    from worldcup_predictor.egie.ml1.trainer import (
        audit_feature_quality,
        build_roadmap_decision,
        compute_market_intelligence_score,
        evaluate_fg_engine,
        evaluate_goal_range,
        evaluate_meta_layer,
        train_lgbm_baselines,
    )

    print("Building unified dataset...")
    df = build_unified_dataset()
    df.to_parquet(ARTIFACTS / "ml1_unified_dataset.parquet", index=False)

    uefa_rows = build_uefa_evaluation_rows()
    inventory = build_dataset_inventory(df, uefa_odds_rows=len(uefa_rows))
    (ARTIFACTS / "ml1_dataset_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print("STEP 1 dataset inventory written")

    feature_quality = audit_feature_quality(df)
    (ARTIFACTS / "ml1_feature_quality.json").write_text(json.dumps(feature_quality, indent=2), encoding="utf-8")
    print("STEP 2 feature quality written")

    lgbm_results = train_lgbm_baselines(df)
    (ARTIFACTS / "ml1_lgbm_results.json").write_text(json.dumps(lgbm_results, indent=2), encoding="utf-8")
    print("STEP 3 LightGBM baselines written")

    fg_results = evaluate_fg_engine(df, settings=None)
    (ARTIFACTS / "ml1_fg_engine_results.json").write_text(json.dumps(fg_results, indent=2), encoding="utf-8")
    print("STEP 4 FG engine written")

    range_results = evaluate_goal_range(df)
    (ARTIFACTS / "ml1_goal_range_results.json").write_text(json.dumps(range_results, indent=2), encoding="utf-8")
    print("STEP 5 goal range written")

    mis = compute_market_intelligence_score(df, settings=None)
    (ARTIFACTS / "ml1_market_intelligence_score.json").write_text(json.dumps(mis, indent=2), encoding="utf-8")
    print("STEP 7 market intelligence score written")

    meta_results = evaluate_meta_layer(df, lgbm_results, fg_results, mis)
    (ARTIFACTS / "ml1_meta_layer_results.json").write_text(json.dumps(meta_results, indent=2), encoding="utf-8")
    print("STEP 6 meta layer written")

    roadmap = build_roadmap_decision(lgbm_results, fg_results, meta_results, mis)
    (ARTIFACTS / "ml1_roadmap_decision.json").write_text(json.dumps(roadmap, indent=2), encoding="utf-8")
    print("STEP 8 roadmap written")

    from scripts._write_phase_ml1_report import write_report

    write_report(
        inventory=inventory,
        feature_quality=feature_quality,
        lgbm_results=lgbm_results,
        fg_results=fg_results,
        range_results=range_results,
        meta_results=meta_results,
        mis=mis,
        roadmap=roadmap,
    )
    print("STEP 9 report written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
