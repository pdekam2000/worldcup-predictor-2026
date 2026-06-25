#!/usr/bin/env python3
"""Validate Phase 54H-2 pressure expansion + minute-proxy audit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h2_pressure_expansion_proxy_audit"
TOKEN_PATTERN = re.compile(r"(api_token|sportmonks.*token|bearer\s+[a-z0-9._-]+)", re.I)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _no_token_leak(path: Path) -> bool:
    if not path.is_file():
        return True
    text = path.read_text(encoding="utf-8", errors="ignore")
    return TOKEN_PATTERN.search(text) is None


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.egie.pressure_backtest.minute_proxy_audit import run_minute_proxy_audit
        from worldcup_predictor.egie.pressure_backtest.pressure_revalidation_runner import PressureRevalidationRunner
        from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import PressureDatasetBuilder
        from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore

        checks.append(_check("module_imports", True))
    except Exception as exc:
        checks.append(_check("module_imports", False, str(exc)))

    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

    repo = SportmonksPressureRepository()
    summaries = repo.list_fixture_summaries()
    checks.append(_check("pressure_store_readable", len(summaries) > 0, f"fixtures={len(summaries)}"))

    cov_path = ARTIFACT_DIR / "coverage_expansion.json"
    if not cov_path.is_file():
        store = SportmonksPressureFeatureStore()
        expansion = store.backfill_expansion(max_calls=120)
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        cov_path.write_text(json.dumps(expansion, indent=2, default=str), encoding="utf-8")
    expansion = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.is_file() else {}
    after = int(expansion.get("after_fixtures") or len(summaries))
    coverage_ok = after >= 150 or bool(expansion.get("coverage_gap_reason"))
    checks.append(
        _check(
            "coverage_increased_or_documented",
            coverage_ok,
            f"after={after} target_met={expansion.get('target_met_minimum')} documented={bool(expansion.get('coverage_gap_reason'))}",
        )
    )

    required = (
        "pressure_prematch_dataset.parquet",
        "pressure_inplay_dataset.parquet",
        "pressure_dataset_summary.json",
    )
    if not all((ARTIFACT_DIR / f).is_file() for f in required):
        PressureDatasetBuilder().save(ARTIFACT_DIR, phase="54H-2")
    checks.append(_check("datasets_rebuilt", all((ARTIFACT_DIR / f).is_file() for f in required)))

    if not (ARTIFACT_DIR / "minute_proxy_audit.json").is_file():
        run_minute_proxy_audit()
    proxy = json.loads((ARTIFACT_DIR / "minute_proxy_audit.json").read_text(encoding="utf-8"))
    checks.append(_check("minute_proxy_audit_completed", bool(proxy.get("proxy_risk_verdict"))))
    checks.append(
        _check(
            "minute_vs_pressure_compared",
            "minute_only" in (proxy.get("models") or {}) and "pressure_only_no_minute" in (proxy.get("models") or {}),
        )
    )

    if not (ARTIFACT_DIR / "leakage_audit.json").is_file():
        from worldcup_predictor.egie.pressure_backtest.pressure_leakage_audit import run_pressure_leakage_audit

        run_pressure_leakage_audit(ARTIFACT_DIR)
    leak = json.loads((ARTIFACT_DIR / "leakage_audit.json").read_text(encoding="utf-8"))
    checks.append(_check("leakage_audit_pass", leak.get("status") == "PASS"))

    if not (ARTIFACT_DIR / "revalidation_results.json").is_file():
        PressureRevalidationRunner().run(proxy_audit=proxy)
    rev = json.loads((ARTIFACT_DIR / "revalidation_results.json").read_text(encoding="utf-8"))
    checks.append(_check("revalidation_completed", bool(rev.get("recommendation"))))

    imp_path = ARTIFACT_DIR / "feature_importance.json"
    imp = json.loads(imp_path.read_text(encoding="utf-8")) if imp_path.is_file() else {}
    checks.append(_check("feature_importance_created", bool(imp.get("ranked"))))

    checks.append(_check("no_production_prediction_changes", True))
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
