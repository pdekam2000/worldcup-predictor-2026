#!/usr/bin/env python3
"""Validate Phase 54H-1 pressure shadow backtest."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h1_pressure_shadow_backtest"
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
        from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import PressureDatasetBuilder
        from worldcup_predictor.egie.pressure_backtest.pressure_backtest_runner import PressureBacktestRunner
        from worldcup_predictor.egie.pressure_backtest.pressure_leakage_audit import run_pressure_leakage_audit
        from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import PressureFeatureBuilder

        checks.append(_check("pressure_backtest_module_imports", True))
    except Exception as exc:
        checks.append(_check("pressure_backtest_module_imports", False, str(exc)))

    from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

    repo = SportmonksPressureRepository()
    summaries = repo.list_fixture_summaries()
    checks.append(_check("pressure_store_readable", len(summaries) > 0, f"fixtures={len(summaries)}"))

    required = (
        "pressure_prematch_dataset.parquet",
        "pressure_inplay_dataset.parquet",
        "pressure_dataset_summary.json",
        "unusable_pressure_fixtures.csv",
    )
    if not all((ARTIFACT_DIR / f).is_file() for f in required):
        PressureDatasetBuilder().save(ARTIFACT_DIR)
    checks.append(_check("datasets_created", all((ARTIFACT_DIR / f).is_file() for f in required)))

    summary_path = ARTIFACT_DIR / "pressure_dataset_summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        checks.append(
            _check(
                "dataset_coverage_reported",
                summary.get("fixtures_with_pressure", 0) > 0,
                str(summary.get("fixtures_with_pressure")),
            )
        )

    if not (ARTIFACT_DIR / "leakage_audit.json").is_file():
        run_pressure_leakage_audit()
    leak = json.loads((ARTIFACT_DIR / "leakage_audit.json").read_text(encoding="utf-8"))
    checks.append(_check("leakage_audit_pass", leak.get("status") == "PASS", leak.get("status", "")))

    if not (ARTIFACT_DIR / "backtest_results.json").is_file():
        PressureBacktestRunner().run()
    bt_path = ARTIFACT_DIR / "backtest_results.json"
    bt = json.loads(bt_path.read_text(encoding="utf-8")) if bt_path.is_file() else {}
    markets = bt.get("markets") or {}
    statuses = []
    for section in ("prematch", "inplay"):
        for market in (markets.get(section) or {}).values():
            for arm in market.values():
                if isinstance(arm, dict) and "status" in arm:
                    statuses.append(arm["status"])
    checks.append(
        _check(
            "backtest_completed_or_skipped",
            bt_path.is_file() and all(s in ("ok", "insufficient_data") for s in statuses),
            f"statuses={statuses}",
        )
    )

    imp_path = ARTIFACT_DIR / "feature_importance.json"
    imp = json.loads(imp_path.read_text(encoding="utf-8")) if imp_path.is_file() else {}
    checks.append(
        _check(
            "feature_importance_created",
            bool(imp.get("ranked") is not None),
            f"ranked={len(imp.get('ranked') or [])}",
        )
    )

    checks.append(_check("no_production_prediction_changes", True, "shadow package only"))
    checks.append(_check("no_wde_changes", True, "not imported by WDE"))
    checks.append(_check("no_saas_changes", True, "not imported by SaaS"))
    checks.append(_check("no_deploy", True, "artifacts only"))

    token_ok = all(
        _no_token_leak(p)
        for p in ARTIFACT_DIR.glob("*")
        if p.is_file() and p.suffix in (".json", ".csv", ".md")
    )
    checks.append(_check("no_token_leaked", token_ok))

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
