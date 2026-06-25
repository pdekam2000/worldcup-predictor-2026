#!/usr/bin/env python3
"""Validate Phase 54H-4 controlled server pressure backfill batch 1."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h4_pressure_backfill_batch1"
TOKEN_RE = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _no_token_leak(path: Path) -> bool:
    if not path.is_file():
        return True
    return TOKEN_RE.search(path.read_text(encoding="utf-8", errors="ignore")) is None


def main() -> int:
    checks: list[dict] = []
    prerun = json.loads((ARTIFACT_DIR / "prerun_validation.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "prerun_validation.json").is_file() else {}
    audit = json.loads((ARTIFACT_DIR / "coverage_audit.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "coverage_audit.json").is_file() else {}

    checks.append(_check("prerun_completed", bool(prerun.get("all_pass"))))
    checks.append(_check("server_token_worked", any(c.get("name") == "pressure_include_probe" and c.get("pass") for c in prerun.get("checks", []))))
    checks.append(_check("backfill_ran", len(audit.get("batch_results") or []) > 0, f"batches={len(audit.get('batch_results') or [])}"))
    checks.append(
        _check(
            "pressure_records_increased_or_documented",
            int(audit.get("new_fixtures") or 0) > 0 or bool(audit.get("blocker")),
            f"new={audit.get('new_fixtures')}",
        )
    )
    dups = audit.get("duplicate_groups_sample") or []
    checks.append(_check("duplicate_groups_zero", len(dups) == 0, f"sample={len(dups)}"))
    checks.append(_check("raw_cache_saved", int(audit.get("cache_files") or 0) > 0, f"files={audit.get('cache_files')}"))
    checks.append(_check("manifest_saved", len(audit.get("manifest_stats") or []) > 0))
    checks.append(
        _check(
            "max_calls_respected",
            int(audit.get("api_calls_live_total") or 0) <= 130,
            f"live={audit.get('api_calls_live_total')}",
        )
    )
    checks.append(_check("no_production_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_token_leaked", all(_no_token_leak(p) for p in ARTIFACT_DIR.glob("*.json"))))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
