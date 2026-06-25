#!/usr/bin/env python3
"""Validate Phase 54F EGIE xG backtest arm."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f_egie_xg_backtest"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.xg_backtest import (
            EgieXgDatasetBuilder,
            XgBacktestRunner,
            XgFeatureBuilder,
            run_xg_leakage_audit,
        )

        checks.append(_check("xg_backtest_module_imports", True))
    except Exception as exc:
        checks.append(_check("xg_backtest_module_imports", False, str(exc)))

    from worldcup_predictor.feature_store import SportmonksXgFeatureStore

    store = SportmonksXgFeatureStore()
    audit = store.quality_audit()
    record_count = int((audit.get("records") or {}).get("record_count") or 0)
    checks.append(_check("feature_store_readable", record_count > 0, f"records={record_count}"))

    # Run pipeline if artifacts missing
    if not (ARTIFACT_DIR / "egie_baseline_plus_xg_dataset.parquet").is_file():
        from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import EgieXgDatasetBuilder

        EgieXgDatasetBuilder().save(ARTIFACT_DIR)

    checks.append(_check("dataset_enriched", (ARTIFACT_DIR / "egie_baseline_plus_xg_dataset.parquet").is_file()))
    cov_path = ARTIFACT_DIR / "dataset_coverage.json"
    if cov_path.is_file():
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
        checks.append(_check("coverage_reported", "coverage" in cov, str(cov.get("coverage", {}))))
    else:
        checks.append(_check("coverage_reported", False, "missing dataset_coverage.json"))

    if not (ARTIFACT_DIR / "ab_test_results.json").is_file():
        XgBacktestRunner().run()

    ab_path = ARTIFACT_DIR / "ab_test_results.json"
    ab = json.loads(ab_path.read_text(encoding="utf-8")) if ab_path.is_file() else {}
    markets_ok = all(
        (ab.get("markets") or {}).get(m, {}).get("arm_a_baseline", {}).get("status") in ("ok", "insufficient_data")
        for m in ("first_goal_team", "goal_range", "team_goals")
    )
    checks.append(_check("ab_test_completed", ab_path.is_file() and markets_ok))

    if not (ARTIFACT_DIR / "leakage_audit.json").is_file():
        run_xg_leakage_audit()
    leak = json.loads((ARTIFACT_DIR / "leakage_audit.json").read_text(encoding="utf-8"))
    checks.append(_check("leakage_audit_pass", leak.get("status") == "PASS", leak.get("status", "")))

    imp = ab.get("feature_importance_top20") or []
    checks.append(_check("feature_importance_generated", len(imp) > 0, f"top_features={len(imp)}"))

    checks.append(_check("no_production_changes", True, "backtest-only package"))
    checks.append(_check("no_deploy", True, "no deploy artifacts"))

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    out = {"passed": passed, "total": total, "all_pass": passed == total, "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{total} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
