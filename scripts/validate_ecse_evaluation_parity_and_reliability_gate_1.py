#!/usr/bin/env python3
"""Validate ECSE-EVALUATION-PARITY-AND-RELIABILITY-GATE-1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "ecse_evaluation_parity_and_reliability_gate_1"
PHASE = "ECSE-EVALUATION-PARITY-AND-RELIABILITY-GATE-1"


def _check(name, ok, detail=""):
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks = []
    for fn in (
        "fixture_parity_audit.json",
        "production_exclusion_reasons.json",
        "parity_repair_export.json",
        "parity_repairs.json",
        "post_repair_parity.json",
        "reliability_dataset.jsonl",
        "hit_vs_miss_forensic.json",
        "segment_reliability_metrics.json",
        "shadow_reliability_gate.json",
        "rank_by_reliability_class.json",
        "workflow.json",
    ):
        checks.append(_check(f"artifact_{fn}", (ART / fn).is_file()))

    checks.append(_check("report", Path("ECSE_EVALUATION_PARITY_AND_RELIABILITY_GATE_1_REPORT.md").is_file()))
    checks.append(_check("parity_owner", Path("ECSE_EVALUATION_PARITY_OWNER_REPORT.md").is_file()))
    checks.append(_check("reliability_owner", Path("ECSE_TOP5_RELIABILITY_GATE_OWNER_REPORT.md").is_file()))

    wf = json.loads((ART / "workflow.json").read_text(encoding="utf-8"))
    rec = wf.get("final_recommendation")
    checks.append(_check("recommendation_valid", rec in {
        "ECSE_PARITY_RESTORED_RELIABILITY_SIGNAL_FOUND",
        "ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL",
        "ECSE_PARITY_BLOCKED_BY_MISSING_HISTORY",
        "ECSE_RELIABILITY_GATE_INSUFFICIENT_SAMPLE",
        "ECSE_DATA_INTEGRITY_ISSUE_FOUND",
    }, str(rec)))

    parity = json.loads((ART / "fixture_parity_audit.json").read_text(encoding="utf-8"))
    checks.append(_check("parity_table_complete", len(parity) >= 1))

    rows = [json.loads(l) for l in (ART / "reliability_dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    checks.append(_check("reliability_pre_match_only", all("target_top5_hit" in r for r in rows)))
    checks.append(_check("no_post_match_leakage_fields", not any("final_score" in r for r in rows)))

    passed = sum(1 for c in checks if c["passed"])
    result = {"phase": PHASE, "checks_passed": passed, "checks_total": len(checks), "validation_ok": passed == len(checks), "checks": checks, "final_recommendation": rec}
    (ART / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
