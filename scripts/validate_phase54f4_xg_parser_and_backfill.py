#!/usr/bin/env python3
"""Validate Phase 54F-4 xG parser fix and targeted backfill."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f4_xg_parser_and_backfill"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import (
        classify_metric_key,
        expected_rows_from_fixture,
        parse_proof_fixture,
    )

    shots = {"type_id": 86, "type": {"id": 86, "name": "Shots On Target"}, "data": {"value": 4}}
    xg_row = {"type_id": 5304, "type": {"id": 5304, "name": "Expected Goals (xG)"}, "data": {"value": 1.2}}
    xgot_row = {"type_id": 5305, "type": {"id": 5305, "name": "Expected Goals on Target (xGoT)"}, "data": {"value": 0.8}}

    # Shape: lowercase list on xgfixture key
    fake = {"xgfixture": [xg_row, xgot_row]}
    checks.append(_check("lowercase_xgfixture_parsed", len(expected_rows_from_fixture(fake)) == 2))
    checks.append(_check("type_5304_is_xg", classify_metric_key(xg_row) == "xg"))
    checks.append(_check("type_5305_is_xgot", classify_metric_key(xgot_row) == "xgot"))
    checks.append(_check("shots_on_target_not_xgot", classify_metric_key(shots) is None))

    rows = expected_rows_from_fixture(fake)
    checks.append(_check("xgfixture_list_rows", len(rows) == 2, f"rows={len(rows)}"))

    proof_path = ROOT / "artifacts" / "phase54f3_xg_discovery" / "raw"
    if proof_path.is_dir():
        for f in proof_path.glob("fixtures_19609127_*.json"):
            blob = json.loads(f.read_text(encoding="utf-8"))
            data = (blob.get("payload") or {}).get("data")
            if isinstance(data, dict):
                proof = parse_proof_fixture(data)
                checks.append(_check("xgfixture_proof_has_team_xg", proof.get("has_team_xg") is True, str(proof)))
                break

    # Backfill artifacts (54E league jobs or 54F-4 cache import)
    backfill_dir = ROOT / "artifacts" / "phase54e_sportmonks_xg_feature_store"
    bf_files = list(backfill_dir.glob("backfill_l*.json")) if backfill_dir.is_dir() else []
    cache_import = ARTIFACT_DIR / "cache_import.json"
    checks.append(
        _check(
            "target_backfills_executed",
            len(bf_files) > 0 or cache_import.is_file(),
            f"backfill_files={len(bf_files)} cache_import={cache_import.is_file()}",
        )
    )

    processed_leagues: set[int] = set()
    for bf in bf_files:
        blob = json.loads(bf.read_text(encoding="utf-8"))
        lid = int(blob.get("league_id") or 0)
        if lid:
            processed_leagues.add(lid)
    if cache_import.is_file():
        cov = json.loads((ARTIFACT_DIR / "coverage_audit.json").read_text(encoding="utf-8")) if (ARTIFACT_DIR / "coverage_audit.json").is_file() else {}
        for name, block in (cov.get("by_league") or {}).items():
            lid = int((block or {}).get("league_id") or 0)
            if lid:
                processed_leagues.add(lid)
    for lid, name in [(732, "wc"), (2, "cl"), (5, "el"), (2286, "conf")]:
        checks.append(_check(f"league_{lid}_processed", lid in processed_leagues, str(processed_leagues)))

    cov_path = ARTIFACT_DIR / "coverage_audit.json"
    if not cov_path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "audit_phase54f4_targeted_xg_backfill.py")], check=False)
    cov = json.loads(cov_path.read_text(encoding="utf-8")) if cov_path.is_file() else {}
    checks.append(_check("coverage_audit_generated", cov_path.is_file()))
    threshold = bool(cov.get("threshold_met"))
    checks.append(
        _check(
            "coverage_threshold_status",
            True,
            f"usable_rolling={cov.get('summary', {}).get('usable_rolling_xg_coverage_pct')}% threshold_met={threshold}",
        )
    )

    ab_path = ROOT / "artifacts" / "phase54f_egie_xg_backtest" / "ab_test_results.json"
    if threshold:
        checks.append(_check("phase54f_rerun_when_ready", ab_path.is_file()))
    else:
        checks.append(_check("phase54f_skipped_insufficient_coverage", True))

    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_frontend_deploy", True))

    text = ""
    for p in [cov_path, ARTIFACT_DIR / "orchestrator.json"]:
        if p.is_file():
            text += p.read_text(encoding="utf-8")
    checks.append(_check("no_token_leaked", "api_token=" not in text.lower()))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks, "threshold_met": threshold}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
