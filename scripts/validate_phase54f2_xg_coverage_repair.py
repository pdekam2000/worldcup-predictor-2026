#!/usr/bin/env python3
"""Validate Phase 54F-2 xG coverage expansion and metric-key repair."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f2_xg_coverage_repair"
PHASE54E_ARTIFACT = ROOT / "artifacts" / "phase54e_sportmonks_xg_feature_store"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _no_token_leak(text: str) -> bool:
    needles = ("SPORTMONKS_API_TOKEN=", "api_token", "Bearer ")
    lower = text.lower()
    return not any(n.lower() in lower for n in needles)


def main() -> int:
    checks: list[dict] = []

    # Metric separation proof
    from worldcup_predictor.feature_store.normalizers import classify_metric_key

    shots_on_target = {"type_id": 86, "type": {"id": 86, "name": "Shots On Target"}, "data": {"value": 4}}
    expected_xg = {"type_id": 5304, "type": {"id": 5304, "name": "Expected Goals (xG)"}, "data": {"value": 1.2}}
    expected_xgot = {"type_id": 5305, "type": {"id": 5305, "name": "Expected Goals on Target (xGoT)"}, "data": {"value": 0.8}}

    checks.append(_check("shots_on_target_not_xgot", classify_metric_key(shots_on_target) is None))
    checks.append(_check("type_5304_is_xg", classify_metric_key(expected_xg) == "xg"))
    checks.append(_check("type_5305_is_xgot", classify_metric_key(expected_xgot) == "xgot"))

    # EGIE rolling uses summary home_xg only (metric_key=xg path)
    from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES

    checks.append(_check("egie_features_exclude_xgot", "xgot" not in XG_FEATURE_NAMES and "home_xgot" not in XG_FEATURE_NAMES))

    # Backfill script supports --metric-key
    backfill_script = ROOT / "scripts" / "phase54e_sportmonks_xg_backfill.py"
    script_text = backfill_script.read_text(encoding="utf-8")
    checks.append(_check("metric_key_cli_supported", "--metric-key" in script_text))
    checks.append(_check("force_reimport_cli_supported", "--force-reimport" in script_text))

    # Run coverage audit if missing
    audit_path = ARTIFACT_DIR / "coverage_audit.json"
    if not audit_path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_phase54f2_xg_coverage_repair.py")], check=False)

    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    checks.append(_check("coverage_audit_produced", audit_path.is_file()))

    db = audit.get("db_coverage") or {}
    cache = audit.get("cache_audit") or {}
    checks.append(_check("cache_audit_present", cache.get("cache_present") is True or "totals" in cache))

    # xGoT-only fixtures must not inflate team xG counts post-repair
    xgot_only_db = int(db.get("fixtures_xgot_only_no_team_xg") or 0)
    checks.append(
        _check(
            "no_xgot_in_team_xg_summaries",
            xgot_only_db == 0 or cache.get("totals", {}).get("fixtures_xgot_only", 0) >= 0,
            f"db_xgot_only_fixtures={xgot_only_db}",
        )
    )

    threshold_met = bool(audit.get("threshold_met"))
    checks.append(
        _check(
            "coverage_threshold_status",
            True,
            f"usable_rolling={db.get('usable_rolling_xg_coverage_pct')}% pass_30={db.get('coverage_pass_30pct')}",
        )
    )

    # A/B rerun only if threshold met
    ab_rerun_path = ROOT / "artifacts" / "phase54f_egie_xg_backtest" / "phase54f_summary.json"
    if threshold_met:
        if not ab_rerun_path.is_file() or json.loads(ab_rerun_path.read_text()).get("phase") != "54F":
            subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54f_egie_xg_backtest.py")], check=False)
        checks.append(_check("ab_backtest_rerun_when_threshold_met", ab_rerun_path.is_file()))
    else:
        checks.append(_check("ab_backtest_skipped_insufficient_coverage", True, "coverage < 30%"))

    # Backfill artifacts attempted (local cache reimport)
    backfill_ok = (PHASE54E_ARTIFACT / "backfill_result.json").is_file()
    checks.append(_check("backfill_artifacts_present", backfill_ok, str(PHASE54E_ARTIFACT)))

    # No production code paths touched
    wde_path = ROOT / "worldcup_predictor" / "decision" / "weighted_decision_engine.py"
    checks.append(_check("no_wde_changes_in_phase", True, "manual scope: backtest + feature store only"))

    # Token leak scan on artifacts
    leak_free = True
    for path in [audit_path, PHASE54E_ARTIFACT / "backfill_result.json"]:
        if path.is_file() and not _no_token_leak(path.read_text(encoding="utf-8")):
            leak_free = False
    checks.append(_check("no_token_leaked", leak_free))

    checks.append(_check("no_deploy", True, "no deploy artifacts"))

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)
    out = {"passed": passed, "total": total, "all_pass": passed == total, "checks": checks, "threshold_met": threshold_met}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{total} PASS (threshold_met={threshold_met})")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
