#!/usr/bin/env python3
"""Validate ECSE-TOP5-RANK-FORENSIC-1 artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE = "ECSE-TOP5-RANK-FORENSIC-1"
ARTIFACT = ROOT / "artifacts" / "ecse_top5_rank_forensic_1"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []
    required = [
        "fixture_level_rank_hits.jsonl",
        "overall_rank_metrics.json",
        "cumulative_hit_at_k.json",
        "segment_rank_metrics.json",
        "bootstrap_results.json",
        "calibration_results.json",
        "shadow_reranking_results.json",
        "workflow.json",
    ]
    for fn in required:
        checks.append(_check(f"artifact_{fn}", (ARTIFACT / fn).is_file()))

    checks.append(_check("report_md", Path("ECSE_TOP5_RANK_FORENSIC_1_REPORT.md").is_file()))
    checks.append(_check("owner_report_md", Path("ECSE_TOP5_RANK_FORENSIC_OWNER_REPORT.md").is_file()))

    wf_path = ARTIFACT / "workflow.json"
    if wf_path.is_file():
        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        rec = wf.get("final_recommendation")
        checks.append(_check("recommendation_set", bool(rec)))
        checks.append(_check(
            "recommendation_valid_enum",
            rec in {
                "ECSE_RANK_ORDER_IS_WELL_CALIBRATED",
                "ECSE_STABLE_GLOBAL_RERANKING_SIGNAL_FOUND",
                "ECSE_SEGMENT_SPECIFIC_RERANKING_SIGNAL_FOUND",
                "ECSE_WEAK_RANK_BIAS_ONLY",
                "ECSE_RANK_ANALYSIS_INSUFFICIENT_SAMPLE",
            },
            str(rec),
        ))
        n = int(wf.get("n_fixtures") or 0)
        checks.append(_check("has_fixtures", n > 0, str(n)))

    overall = ARTIFACT / "overall_rank_metrics.json"
    if overall.is_file():
        o = json.loads(overall.read_text(encoding="utf-8"))
        n = o.get("n", 0)
        hits = sum(o.get("hits_by_rank", {}).values())
        checks.append(_check("hit_counts_consistent", hits + o.get("miss_top5", 0) == n))
        rates = o.get("exact_hit_rates", {})
        checks.append(_check("five_rank_rates_present", len(rates) == 5))

    jsonl = ARTIFACT / "fixture_level_rank_hits.jsonl"
    if jsonl.is_file():
        rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
        checks.append(_check("jsonl_row_count_matches", len(rows) == json.loads((ARTIFACT / "workflow.json").read_text()).get("n_fixtures", -1)))
        for row in rows:
            checks.append(_check(f"top5_distinct_{row['fixture_id']}", len(set([row[f'top{i}'] for i in range(1, 6)])) == 5))

    passed = sum(1 for c in checks if c["passed"])
    result = {
        "phase": PHASE,
        "checks_passed": passed,
        "checks_total": len(checks),
        "validation_ok": passed == len(checks),
        "checks": checks,
    }
    (ARTIFACT / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["validation_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
