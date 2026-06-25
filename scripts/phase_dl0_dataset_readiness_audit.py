#!/usr/bin/env python3
"""PHASE DL-0 — Deep Learning Dataset Readiness Audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    from worldcup_predictor.egie.dl_readiness.dataset_audit import (
        audit_dataset_inventory,
        audit_feature_coverage,
        audit_market_readiness,
        build_roadmap_decision,
        check_dl_thresholds,
        match_architectures,
        rank_dl_suitability,
    )

    inventory = audit_dataset_inventory()
    (ARTIFACTS / "dl_dataset_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print("STEP 1 inventory written")

    market_readiness = audit_market_readiness(inventory)
    (ARTIFACTS / "dl_market_readiness.json").write_text(json.dumps(market_readiness, indent=2), encoding="utf-8")
    print("STEP 2 market readiness written")

    feature_coverage = audit_feature_coverage(inventory)
    (ARTIFACTS / "dl_feature_coverage.json").write_text(json.dumps(feature_coverage, indent=2), encoding="utf-8")
    print("STEP 3 feature coverage written")

    suitability = rank_dl_suitability(market_readiness, feature_coverage)
    (ARTIFACTS / "dl_suitability_ranking.json").write_text(json.dumps(suitability, indent=2), encoding="utf-8")
    print("STEP 4 suitability ranking written")

    architecture = match_architectures(market_readiness)
    (ARTIFACTS / "dl_architecture_matching.json").write_text(json.dumps(architecture, indent=2), encoding="utf-8")
    print("STEP 5 architecture matching written")

    thresholds = check_dl_thresholds(inventory)
    (ARTIFACTS / "dl_threshold_check.json").write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
    print("STEP 6 threshold check written")

    roadmap = build_roadmap_decision(suitability, thresholds, inventory)
    (ARTIFACTS / "dl_roadmap_decision.json").write_text(json.dumps(roadmap, indent=2), encoding="utf-8")
    print("STEP 7 roadmap written")

    from scripts._write_phase_dl0_report import write_report

    write_report(
        inventory=inventory,
        market_readiness=market_readiness,
        feature_coverage=feature_coverage,
        suitability=suitability,
        architecture=architecture,
        thresholds=thresholds,
        roadmap=roadmap,
    )
    print("STEP 8 report written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
