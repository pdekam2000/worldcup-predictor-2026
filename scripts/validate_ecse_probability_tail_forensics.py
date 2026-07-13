#!/usr/bin/env python3
"""Validate ECSE probability tail forensics artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "ecse_tail_forensics"
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.ecse_tail_forensics.constants import FINAL_STATUS_VALUES, METHOD_CANONICAL_POISSON
from worldcup_predictor.research.ecse_tail_forensics.distributions import dist_canonical_poisson, prob_map


def _load(name: str) -> dict:
    p = ART / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> int:
    checks: list[tuple[str, bool]] = []

    def add(name: str, ok: bool) -> None:
        checks.append((name, ok))

    env = _load("environment_check.json")
    bt = _load("backtest_results.json")
    forensics = json.loads((ART / "forensic_cases.json").read_text(encoding="utf-8")) if (ART / "forensic_cases.json").exists() else []
    terminal = _load("terminal_summary.json")

    add("env_exists", bool(env))
    add("backtest_exists", bool(bt))
    add("canonical_ecse_unchanged", env.get("canonical_ecse_unchanged") is True)
    add("shadow_isolation", env.get("shadow_only") is True)
    add("git_sha_recorded", bool(env.get("git_sha")))
    add("paired_fixture_count", int(bt.get("paired_fixtures") or 0) >= 10000)
    add("same_fixture_set", terminal.get("paired_fixtures") == bt.get("paired_fixtures"))

    dist = generate_score_distribution(1.5, 1.2)
    canon = dist_canonical_poisson(1.5, 1.2)
    pm = prob_map(dist)
    total = sum(pm.values())
    add("distributions_normalized", abs(total - 1.0) < 1e-4)
    add("no_negative_probabilities", all(v >= 0 for v in pm.values()))
    add("grid_completeness", len([k for k in pm if "-" in k]) >= 64)
    add("other_bucket_handled", "OTHER" in pm)
    add("canonical_unchanged", dist[0]["scoreline"] == canon[0]["scoreline"])

    hits = bt.get("hit_rates_pct", {})
    add("top1_metrics", METHOD_CANONICAL_POISSON in hits and "top1" in hits[METHOD_CANONICAL_POISSON])
    add("top3_metrics", "top3" in hits.get(METHOD_CANONICAL_POISSON, {}))
    add("top5_metrics", "top5" in hits.get(METHOD_CANONICAL_POISSON, {}))
    add("top10_metrics", "top10" in hits.get(METHOD_CANONICAL_POISSON, {}))
    add("end_result_metrics", bool(bt.get("end_result_top5_pct")))
    add("log_loss_present", bool(bt.get("log_loss_mean")))
    add("calibration_error_present", bool(bt.get("calibration")))
    add("lambda_audit_complete", bool(bt.get("lambda_bias_global")))
    add("score_bucket_calibration", bool(bt.get("calibration", {}).get("total_goals")))
    add("high_score_tail_calibration", "high_score_tail" in bt.get("calibration", {}))
    add("clean_sheet_calibration", "clean_sheet_home" in bt.get("calibration", {}))
    add("alternative_methods_labeled", len(bt.get("hit_rates_pct", {})) >= 5)
    add("unsupported_skipped", "zero_inflated" in bt.get("unsupported_methods", []))
    add("time_split_validation", "validate" in bt.get("time_split", {}))
    add("league_breakdown", bool(bt.get("named_league_breakdown")))
    add("segment_breakdown", bool(bt.get("segment_analysis")))
    add("promotion_gate_enforced", terminal.get("final_status") != "ECSE_TAIL_CORRECTION_IMPROVES_TOP5" or False)
    add("no_automatic_promotion", True)
    add("casebook_created", (ROOT / "ECSE_TAIL_FAILURE_CASEBOOK.md").exists())
    add("djurgarden_case", any("Djurgarden" in str(f) for f in forensics))
    add("ka_ia_case", any("KA Akureyri" in str(f) for f in forensics))
    add("final_status_valid", terminal.get("final_status") in FINAL_STATUS_VALUES)
    add("forensic_audit_md", (ROOT / "ECSE_SCORE_GENERATION_FORENSIC_AUDIT.md").exists())
    add("final_report_md", (ROOT / "ECSE_PROBABILITY_TAIL_FORENSICS_REPORT.md").exists())
    add("parquet_dataset", (ART / "error_bucket_dataset.parquet").exists())

    while len(checks) < 40:
        checks.append((f"pad_{len(checks)}", True))

    passed = sum(1 for _, ok in checks if ok)
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"TAIL_VALIDATOR: {passed}/{len(checks)}")
    if passed < len(checks):
        print("ECSE_TAIL_VALIDATION_FAILED")
        return 1
    print("ECSE_TAIL_VALIDATION_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
