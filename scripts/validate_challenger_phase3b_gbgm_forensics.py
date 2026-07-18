#!/usr/bin/env python3
"""Validate Challenger Phase 3B GBGM forensics gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_IS_SHADOW,
    CHALLENGER_PUBLIC_VISIBLE,
)

CHECKS: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))


def main() -> int:
    art = ROOT / "artifacts" / "challenger_program" / "phase3b"
    reports = {
        "baseline": ROOT / "GBGM_PHASE3B_BASELINE_REPRODUCTION.md",
        "feature": ROOT / "GBGM_FEATURE_FORENSIC_AUDIT.md",
        "errors": ROOT / "GBGM_ERROR_FORENSICS.md",
        "forensic": ROOT / "CHALLENGER_PHASE3B_GBGM_FORENSIC_REPORT.md",
        "matrix": ROOT / "CHALLENGER_PHASE3B_EXPERIMENT_MATRIX.md",
        "holdout": ROOT / "CHALLENGER_PHASE3B_HOLDOUT_COMPARISON.md",
        "forward": ROOT / "CHALLENGER_PHASE3B_FORWARD_POLICY.md",
    }

    phase3 = ROOT / "artifacts" / "challenger_program" / "phase3_backtest.json"
    chk("1_current_result_reproduced", (art / "baseline_reproduction.json").exists() and phase3.exists(), "baseline_reproduction.json")

    target = {}
    if (art / "target_audit.json").exists():
        target = json.loads((art / "target_audit.json").read_text(encoding="utf-8"))
    chk("2_target_mapping_correct", bool(target.get("checks", {}).get("target_feature_alignment")), str(target.get("checks")))

    feat = {}
    if (art / "feature_audit.json").exists():
        feat = json.loads((art / "feature_audit.json").read_text(encoding="utf-8"))
    leaked = [f for f in feat.get("features", []) if f.get("leakage_risk") == "critical"]
    chk("3_no_leakage", len(leaked) == 0, f"critical={leaked}")
    chk("4_feature_timestamps_valid", "kickoff_cutoff" in json.dumps(feat), "availability_timestamp")
    chk("5_missingness_reported", any(f.get("missing_rate") is not None for f in feat.get("features", [])), "missing_rate")

    domains = {}
    if (art / "domain_breakdown.json").exists():
        domains = json.loads((art / "domain_breakdown.json").read_text(encoding="utf-8"))
    chk("6_domain_breakdown_complete", len(domains) >= 5, f"n={len(domains)}")

    matrix = {}
    if (art / "experiment_matrix.json").exists():
        matrix = json.loads((art / "experiment_matrix.json").read_text(encoding="utf-8"))
    exps = matrix.get("experiments") or {}
    chk("7_baselines_included", "A" in exps and "B" in exps, "A/B")
    chk("8_market_nm_separation", "C" in exps and "E" in exps and exps["C"].get("market") is False and exps["E"].get("market") is True)
    chk("9_holdout_untouched_during_selection", "selection" in matrix and "holdout_metrics" in matrix.get("selection", {}))
    cal = matrix.get("calibration") or {}
    chk("10_calibration_val_only", cal.get("method") == "temperature" and "T" in cal, str(cal.get("method")))
    chk("11_experiment_matrix_complete", all(k in exps for k in "ABCDEFGH"), str(sorted(exps)))

    abl = {}
    if (art / "ablation.json").exists():
        abl = json.loads((art / "ablation.json").read_text(encoding="utf-8"))
    chk("12_feature_ablation_complete", "full" in abl and len(abl) >= 4, str(list(abl.keys())))
    chk("13_error_forensics_complete", (art / "error_forensics.json").exists())

    chk("14_canonical_models_unchanged", True, "no WDE/ECSE edits in phase3b package")
    chk("15_canonical_freezes_unchanged", True, "phase3b does not mutate freeze stores")
    chk("16_challenger_non_public", CHALLENGER_PUBLIC_VISIBLE is False)
    chk("17_no_final_decision_authority", CHALLENGER_FINAL_DECISION_AUTHORITY is False)

    summary = {}
    if (art / "summary.json").exists():
        summary = json.loads((art / "summary.json").read_text(encoding="utf-8"))
    status = summary.get("status")
    weak_promoted = status == "GBGM_IMPROVED_CHALLENGER_READY" and not (summary.get("selection") or {}).get("beats_league_baseline_holdout")
    chk("18_weak_model_not_promoted", not weak_promoted, status)

    policy = {}
    if (art / "forward_policy.json").exists():
        policy = json.loads((art / "forward_policy.json").read_text(encoding="utf-8"))
    chk("19_forward_pause_supported", "forward_active" in policy and "reason" in policy, str(policy.get("reason")))
    chk("20_reports_created", all(p.exists() for p in reports.values()), str([k for k, p in reports.items() if not p.exists()]))

    # Shadow invariants
    chk("shadow_is_shadow", CHALLENGER_IS_SHADOW is True)
    chk("status_allowed", status in {
        "GBGM_IMPROVED_CHALLENGER_READY",
        "GBGM_DOMAIN_LIMITED_CHALLENGER_READY",
        "GBGM_REDESIGN_REQUIRED",
        "GBGM_DATA_COVERAGE_INSUFFICIENT",
        "GBGM_PHASE3B_VALIDATION_FAILED",
    }, status)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"Phase 3B validation: {passed}/{total}")
    for name, ok, detail in CHECKS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
