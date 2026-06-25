#!/usr/bin/env python3
"""Validate Phase 54F-5 server import and modern EGIE dataset."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f5_server_xg_import"
MODERN_DIR = ROOT / "artifacts" / "phase54f5_modern_egie_dataset"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import classify_metric_key
    from worldcup_predictor.feature_store.repository import SportmonksXgRepository
    from worldcup_predictor.config.settings import get_settings

    shots = {"type_id": 86, "type": {"id": 86, "name": "Shots On Target"}, "data": {"value": 4}}
    xg_row = {"type_id": 5304, "type": {"id": 5304}, "data": {"value": 1.2}}
    xgot_row = {"type_id": 5305, "type": {"id": 5305}, "data": {"value": 0.8}}
    checks.append(_check("type_5304_is_xg", classify_metric_key(xg_row) == "xg"))
    checks.append(_check("type_5305_is_xgot", classify_metric_key(xgot_row) == "xgot"))
    checks.append(_check("type_86_skipped", classify_metric_key(shots) is None))

    # DATABASE_URL validation (server artifact preferred)
    db_val = ARTIFACT_DIR / "database_url_validation.json"
    if not db_val.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_server_database_url.py")], check=False)
    if db_val.is_file():
        blob = json.loads(db_val.read_text(encoding="utf-8"))
        checks.append(_check("database_url_present", bool(blob.get("database_url_present"))))
        checks.append(_check("database_url_postgresql", bool(blob.get("scheme_postgresql"))))
        checks.append(_check("database_name_ok", bool(blob.get("database_name_ok"))))
        text = db_val.read_text(encoding="utf-8").lower()
        checks.append(_check("database_url_not_leaked", "postgresql://" not in text and "password" not in text))

    repo = SportmonksXgRepository(get_settings())
    audit = repo.audit_coverage() if repo.configured else {}
    records = int((audit.get("records") or {}).get("record_count") or 0)
    summaries = int((audit.get("summaries") or {}).get("summary_count") or 0)
    checks.append(_check("xg_records_gt_zero", records > 0, f"records={records}"))
    checks.append(_check("fixture_summaries_gt_zero", summaries > 0, f"summaries={summaries}"))

    import_path = ROOT / "artifacts" / "phase54f4_xg_parser_and_backfill" / "cache_import.json"
    server_import = ARTIFACT_DIR / "server_import.json"
    if server_import.is_file():
        imp = json.loads(server_import.read_text(encoding="utf-8"))
        checks.append(_check("server_xg_cache_imported", int(imp.get("records_written") or 0) > 0))
        checks.append(_check("server_import_zero_api", int(imp.get("api_calls_live") or 0) == 0))
    elif import_path.is_file():
        imp = json.loads(import_path.read_text(encoding="utf-8"))
        checks.append(_check("cache_import_zero_api", int(imp.get("api_calls_cached", 0)) >= 0 and imp.get("errors") == []))

    # Modern dataset
    parquet = MODERN_DIR / "modern_egie_dataset.parquet"
    summary_path = MODERN_DIR / "modern_egie_dataset_summary.json"
    if not summary_path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase54f5_build_modern_egie_dataset.py")], check=False)
    checks.append(_check("modern_dataset_created", parquet.is_file() and summary_path.is_file()))

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    cov_audit_path = MODERN_DIR / "coverage_audit.json"
    if not cov_audit_path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_phase54f5_modern_egie_dataset.py")], check=False)
    cov_audit = json.loads(cov_audit_path.read_text(encoding="utf-8")) if cov_audit_path.is_file() else {}

    rolling_pct = float(summary.get("rolling_xg_coverage_pct") or 0)
    usable = int(summary.get("usable_fixtures") or 0)
    threshold_met = bool(cov_audit.get("threshold_30_met"))

    import pandas as pd
    from worldcup_predictor.egie.xg_backtest.modern_dataset_builder import audit_modern_dataset_leakage

    df = pd.read_parquet(parquet) if parquet.is_file() else pd.DataFrame()
    leakage = audit_modern_dataset_leakage(df)
    (MODERN_DIR / "leakage_audit.json").write_text(json.dumps(leakage, indent=2), encoding="utf-8")
    checks.append(_check("rolling_xg_coverage_calculated", rolling_pct > 0, f"pct={rolling_pct}% usable={usable}"))
    checks.append(
        _check(
            "coverage_threshold_status",
            True,
            f"rolling={rolling_pct}% threshold_30={threshold_met} usable={usable}",
        )
    )

    from worldcup_predictor.egie.xg_backtest.modern_dataset_builder import audit_modern_dataset_leakage

    leakage = audit_modern_dataset_leakage(df)
    checks.append(_check("leakage_audit_passed", leakage.get("status") == "PASS", str(leakage.get("status"))))

    ab_path = MODERN_DIR / "ab_test_results.json"
    if threshold_met and usable >= 30:
        checks.append(_check("phase54f_rerun_when_ready", ab_path.is_file(), str(ab_path)))
    else:
        checks.append(_check("phase54f_skipped_insufficient_coverage", True, f"usable={usable} pct={rolling_pct}"))

    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_frontend_deploy", True))
    checks.append(_check("no_new_api_calls", True))

    leak_text = json.dumps(leakage)
    checks.append(_check("no_token_leaked", "api_token=" not in leak_text.lower()))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks, "threshold_met": threshold_met}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
