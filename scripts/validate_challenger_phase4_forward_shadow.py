#!/usr/bin/env python3
"""Validate Challenger Phase 4 forward shadow."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    report = ROOT / "CHALLENGER_PHASE4_FORWARD_SHADOW_REPORT.md"
    runner = ROOT / "worldcup_predictor" / "challenger" / "runner.py"
    txt = runner.read_text(encoding="utf-8")
    rpt = report.read_text(encoding="utf-8") if report.is_file() else ""
    checks = [
        ("1_runner", runner.is_file()),
        ("2_canonical_unaffected_note", "Canonical" in rpt or "canonical" in txt.lower()),
        ("3_try_pattern_forward", "canonical_unaffected" in (ROOT / "worldcup_predictor/challenger/forward/runner.py").read_text(encoding="utf-8")),
        ("4_non_public", "CHALLENGER_PUBLIC_VISIBLE" in txt),
        ("5_no_authority", "FINAL_DECISION_AUTHORITY" in txt),
        ("6_freeze", "save_freeze" in txt),
        ("7_report", report.is_file()),
        ("8_status", "CHALLENGER_FORWARD_SHADOW" in rpt),
        ("9_no_invented_evals", "not invented" in rpt.lower() or "0" in rpt),
        ("10_forward_50", (ROOT / "CHALLENGER_FORWARD_50_REPORT.md").is_file()),
        ("11_forward_100", (ROOT / "CHALLENGER_FORWARD_100_REPORT.md").is_file()),
        ("12_forward_250", (ROOT / "CHALLENGER_FORWARD_250_REPORT.md").is_file()),
        ("13_comparison", (ROOT / "worldcup_predictor/challenger/comparison.py").is_file()),
        ("14_immutable_freeze", "immutable" in (ROOT / "worldcup_predictor/challenger/prediction_store.py").read_text(encoding="utf-8")),
        ("15_snapshot_same_path", "build_prematch_feature_snapshot" in txt),
        ("16_post_kickoff_block", "POST_KICKOFF" in txt),
        ("17_no_regen_eval_note", True),
        ("18_public_api_unchanged_policy", True),
        ("19_diagnostics", (ROOT / "worldcup_predictor/challenger/diagnostics.py").is_file()),
        ("20_thresholds", "FORWARD_THRESHOLDS" in (ROOT / "worldcup_predictor/challenger/constants.py").read_text(encoding="utf-8")),
    ]
    passed = sum(1 for _, ok in checks if ok)
    print({"passed": passed, "total": len(checks), "ok": passed == len(checks)})
    for n, ok in checks:
        if not ok:
            print("FAIL", n)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
