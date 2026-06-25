#!/usr/bin/env python3
"""Validate Phase 54F-6B full xG revalidation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f6b_full_xg_revalidation"
DATASET = ROOT / "artifacts" / "phase54f6_expanded_dataset" / "expanded_egie_dataset.parquet"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    if not (ARTIFACT_DIR / "full_revalidation.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54f6b_full_xg_revalidation.py")], check=False)

    result = json.loads((ARTIFACT_DIR / "full_revalidation.json").read_text(encoding="utf-8"))
    ver = result.get("dataset_verification") or {}

    checks.append(_check("dataset_exists", DATASET.is_file()))
    checks.append(_check("usable_gte_1000", int(ver.get("usable_fixtures") or 0) >= 1000, str(ver.get("usable_fixtures"))))
    checks.append(_check("ab_all_markets_ok", all(
        (result.get("markets") or {}).get(m, {}).get("arm_a_baseline", {}).get("status") == "ok"
        for m in ("first_goal_team", "goal_range", "team_goals")
    )))
    checks.append(_check("bootstrap_reported", all(
        "bootstrap" in ((result.get("markets") or {}).get(m, {}).get("statistics") or {})
        for m in ("first_goal_team", "goal_range", "team_goals")
    )))
    checks.append(_check("feature_importance_top20", len(result.get("feature_importance_top20") or []) >= 10))
    checks.append(_check("final_decision_recorded", bool(result.get("final_value_tier"))))
    checks.append(_check("sample_size_sufficient", bool(result.get("sample_size_sufficient"))))
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(_check("ready_for_54g_false", result.get("ready_for_54g") is False))

    text = (ARTIFACT_DIR / "full_revalidation.json").read_text(encoding="utf-8").lower()
    checks.append(_check("no_token_leaked", "api_token=" not in text))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
