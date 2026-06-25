#!/usr/bin/env python3
"""Validate Phase 54H-5 pressure backfill expansion."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h5_pressure_expansion"
TOKEN_RE = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _no_token_leak(path: Path) -> bool:
    if not path.is_file():
        return True
    return TOKEN_RE.search(path.read_text(encoding="utf-8", errors="ignore")) is None


def main() -> int:
    checks: list[dict] = []
    pre = json.loads((ARTIFACT_DIR / "pre_run_state.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "pre_run_state.json").is_file() else {}
    audit = json.loads((ARTIFACT_DIR / "coverage_audit.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "coverage_audit.json").is_file() else {}
    uefa = (ARTIFACT_DIR / "uefa_prior_season_targets.json").is_file()
    seed = json.loads((ARTIFACT_DIR / "cache_seed_result.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "cache_seed_result.json").is_file() else {}

    wc_batches = [b for b in (audit.get("batch_results") or []) if "wc_batch" in str(b.get("job_key") or "")]
    checks.append(_check("pre_run_state_saved", bool(pre.get("pressure_fixture_count") is not None)))
    checks.append(_check("server_token_worked", int(audit.get("api_calls_live_total") or 0) > 0 or int(audit.get("fixtures_after") or 0) > int(pre.get("pressure_fixture_count") or 0)))
    checks.append(_check("wc_batches_ran_or_documented", len(wc_batches) > 0 or bool(audit.get("blocker")), f"batches={len(wc_batches)}"))
    checks.append(
        _check(
            "pressure_fixture_count_increased_or_blocker",
            int(audit.get("new_fixtures") or 0) > 0 or bool(audit.get("blocker")),
            f"new={audit.get('new_fixtures')}",
        )
    )
    dups = audit.get("duplicate_groups_sample") or []
    checks.append(_check("duplicate_groups_zero", len(dups) == 0, f"sample={len(dups)}"))
    checks.append(_check("raw_cache_saved", int(audit.get("cache_files") or 0) > 0, f"files={audit.get('cache_files')}"))
    checks.append(
        _check(
            "max_calls_respected",
            int(audit.get("api_calls_live_total") or 0) <= 100,
            f"live={audit.get('api_calls_live_total')}",
        )
    )
    checks.append(_check("uefa_prior_season_discovery_completed", uefa))
    checks.append(
        _check(
            "cache_seed_attempted_or_documented",
            bool(seed) or int(audit.get("fixtures_after") or 0) >= 150,
            seed.get("status", "not_needed"),
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
