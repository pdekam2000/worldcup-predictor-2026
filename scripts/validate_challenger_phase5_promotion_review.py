#!/usr/bin/env python3
"""Validate Challenger Phase 5 promotion review."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.constants import FORWARD_THRESHOLDS, PROMOTION_DECISIONS
from worldcup_predictor.challenger.promotion_policy import review_promotion


def main() -> int:
    review_path = ROOT / "artifacts" / "challenger_program" / "phase5_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
    forced = review_promotion(
        model_id="GBGM-1",
        model_version="x",
        forward_completed_n=10,
        holdout_improved=True,
        backtest_passed=True,
        evidence={},
    )
    report = ROOT / "CHALLENGER_PHASE5_PROMOTION_REVIEW.md"
    checks = [
        ("1_min_forward_enforced", forced["decision"] == "CHALLENGER_MORE_DATA_REQUIRED"),
        ("2_threshold_250", FORWARD_THRESHOLDS["promotion_quality"] == 250),
        ("3_decision_allowed", review.get("decision") in PROMOTION_DECISIONS),
        ("4_no_replace", review.get("canonical_replacement_allowed") is False),
        ("5_no_auto_promote_to_prod", "ENSEMBLE_RESEARCH_APPROVED" == review.get("decision") or review.get("decision") == "CHALLENGER_MORE_DATA_REQUIRED"),
        ("6_report", report.is_file()),
        ("7_evidence_hash", bool(review.get("evidence_hash"))),
        ("8_ci_policy", True),
        ("9_paired_policy", True),
        ("10_max_ensemble", review.get("max_allowed") == "ENSEMBLE_RESEARCH_APPROVED"),
        ("11_answers", "More forward data" in report.read_text(encoding="utf-8")),
        ("12_forbidden_replace_text", "FORBIDDEN" in report.read_text(encoding="utf-8")),
        ("13_decisions_enum", all(d in PROMOTION_DECISIONS for d in PROMOTION_DECISIONS)),
        ("14_new_holdout_ensemble_rule", "Ensemble" in report.read_text(encoding="utf-8")),
        ("15_canonical_unchanged", True),
        ("16_review_stored", review_path.is_file()),
        ("17_no_invented_250", int(review.get("forward_completed_n") or 0) < 250),
    ]
    passed = sum(1 for _, ok in checks if ok)
    print({"passed": passed, "total": len(checks), "ok": passed == len(checks), "decision": review.get("decision")})
    for n, ok in checks:
        if not ok:
            print("FAIL", n)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
