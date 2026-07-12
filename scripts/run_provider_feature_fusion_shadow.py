#!/usr/bin/env python3
"""Run provider feature fusion shadow audit and experiments (stored data only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.provider_feature_fusion.ablation import build_ablation_report
from worldcup_predictor.research.provider_feature_fusion.coverage_audit import audit_coverage
from worldcup_predictor.research.provider_feature_fusion.dataset_builder import build_shadow_dataset
from worldcup_predictor.research.provider_feature_fusion.experiments import run_fusion_experiments
from worldcup_predictor.research.provider_feature_fusion.importance import compute_feature_importance
from worldcup_predictor.research.provider_feature_fusion.leakage import registry_dict
from worldcup_predictor.research.provider_feature_fusion.report_generator import generate_all_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider feature fusion shadow audit")
    parser.add_argument("--force-dataset", action="store_true")
    parser.add_argument("--skip-experiments", action="store_true")
    args = parser.parse_args()

    report: dict = {"phase": "PROVIDER-FEATURE-FUSION-SHADOW", "steps": {}}

    report["steps"]["leakage_registry"] = {"count": len(registry_dict())}
    report["steps"]["coverage"] = audit_coverage()
    report["steps"]["dataset"] = build_shadow_dataset(force=args.force_dataset)

    if not args.skip_experiments:
        report["steps"]["experiments"] = run_fusion_experiments()
        report["steps"]["ablation"] = build_ablation_report(report["steps"]["experiments"])
        report["steps"]["importance"] = compute_feature_importance()

    report["steps"]["reports"] = generate_all_reports()
    report["provider_calls_made"] = 0
    report["production_modified"] = False

    out = ROOT / "artifacts/provider_feature_fusion/run_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
