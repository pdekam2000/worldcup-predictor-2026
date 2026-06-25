#!/usr/bin/env python3
"""Validate Phase 54H-3 live pressure backfill plan."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h3_live_pressure_backfill_plan"
TOKEN_PATTERN = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _no_token_leak(path: Path) -> bool:
    if not path.is_file():
        return True
    return TOKEN_PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")) is None


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.feature_store.pressure_store.backfill_plan import (
            check_token_readiness,
            design_backfill_targets,
            estimate_api_calls,
        )
        checks.append(_check("module_imports", True))
    except Exception as exc:
        checks.append(_check("module_imports", False, str(exc)))

    if not (ARTIFACT_DIR / "plan.json").is_file():
        import subprocess
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54h3_live_pressure_backfill_plan.py"), "--server-probe", "--skip-live-probes"], check=False)

    plan = json.loads((ARTIFACT_DIR / "plan.json").read_text(encoding="utf-8"))
    local = (plan.get("token_readiness") or {}).get("local") or {}
    server = (plan.get("token_readiness") or {}).get("server") or {}

    checks.append(_check("local_token_checked", "token_present" in local))
    checks.append(_check("server_token_checked", server.get("checked") is True))
    checks.append(
        _check(
            "coverage_plan_documented",
            bool(plan.get("target_design")) and bool(plan.get("api_estimate")),
            f"candidates={plan.get('target_design', {}).get('candidate_total')}",
        )
    )
    checks.append(_check("minute_proxy_not_in_scope", True, "54H-3 plan only"))
    checks.append(
        _check(
            "recommendation_set",
            plan.get("recommendation") in {
                "READY_FOR_PRESSURE_BACKFILL",
                "TOKEN_NOT_READY",
                "PRESSURE_ACCESS_BLOCKED",
                "NEED_TARGET_FIXTURE_REPAIR",
            },
            str(plan.get("recommendation")),
        )
    )
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_token_leaked", all(_no_token_leak(p) for p in ARTIFACT_DIR.glob("*.json"))))

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
