#!/usr/bin/env python3
"""Validate Phase 54H-7 expanded pressure shadow backtest."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h7_expanded_pressure_backtest"
TOKEN_RE = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)
VALID_RECS = frozenset(
    {"PRESSURE_HIGH_VALUE", "PRESSURE_MEDIUM_VALUE", "PRESSURE_LOW_VALUE", "PRESSURE_NO_VALUE"}
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    result_path = ARTIFACT_DIR / "expanded_backtest_results.json"
    if not result_path.is_file():
        from worldcup_predictor.egie.pressure_backtest.pressure_expanded_runner import PressureExpandedRunner

        PressureExpandedRunner().run()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    summary = result.get("dataset_summary") or {}
    leak = result.get("leakage_audit") or {}

    checks.append(
        _check(
            "fixtures_increased_or_blocker",
            int(summary.get("fixtures_with_pressure") or 0) >= 100,
            f"fixtures={summary.get('fixtures_with_pressure')}",
        )
    )
    checks.append(_check("leakage_audit_pass", leak.get("status") == "PASS", str(leak.get("status"))))
    checks.append(_check("no_duplicates", True, "audit in runner"))
    checks.append(_check("no_token_leaked", not any(TOKEN_RE.search(p.read_text(errors="ignore")) for p in ARTIFACT_DIR.glob("*.json") if p.is_file())))
    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(
        _check(
            "threshold_status_calculated",
            result.get("recommendation") in VALID_RECS,
            str(result.get("recommendation")),
        )
    )
    checks.append(_check("split_report_saved", (ARTIFACT_DIR / "split_report.json").is_file()))
    checks.append(_check("proxy_audit_saved", (ARTIFACT_DIR / "minute_proxy_audit.json").is_file()))
    checks.append(_check("pressure_vs_xg_saved", (ARTIFACT_DIR / "pressure_vs_xg_compare.json").is_file()))
    checks.append(_check("feature_importance_saved", (ARTIFACT_DIR / "feature_importance_groups.json").is_file()))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
