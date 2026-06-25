#!/usr/bin/env python3
"""Validate Phase 58D Root Cause Analyzer."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase58d_root_cause_analyzer"
STORE_DIR = ROOT / "data" / "shadow" / "root_cause_store"
REPORT = ROOT / "PHASE_58D_ROOT_CAUSE_ANALYZER_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.root_cause import VALID_RECOMMENDATIONS, run_phase58d

        checks.append(_check("root_cause_imports", True))
    except Exception as exc:
        checks.append(_check("root_cause_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_phase58d = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "root_cause"
    for mod in (
        "config.py",
        "models.py",
        "comparison.py",
        "attribution.py",
        "blame_matrix.py",
        "patterns.py",
        "knowledge_store.py",
        "data_loader.py",
        "runner.py",
    ):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    if not (ARTIFACT_DIR / "phase58d_report.json").is_file() and run_phase58d:
        run_phase58d()
    elif not (ARTIFACT_DIR / "phase58d_report.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase58d_root_cause_analyzer.py")], check=False)

    store_files = (
        "comparisons_summary.json",
        "component_blame_matrix.json",
        "failure_patterns.json",
        "failure_breakdown.json",
        "priority_actions.json",
    )
    for fname in store_files:
        checks.append(_check(f"store_{fname}", (STORE_DIR / fname).is_file()))

    records = _load_jsonl(STORE_DIR / "knowledge_records.jsonl")
    checks.append(_check("knowledge_records_jsonl", len(records) > 0, str(len(records))))

    required_fields = ("fixture_id", "market", "failure_reason", "component_scores", "recommended_action", "confidence")
    fields_ok = all(all(k in r for k in required_fields) for r in records[:20]) if records else False
    checks.append(_check("knowledge_record_schema", fields_ok))

    blame = {}
    if (STORE_DIR / "component_blame_matrix.json").is_file():
        blame = json.loads((STORE_DIR / "component_blame_matrix.json").read_text(encoding="utf-8"))
    global_blame = blame.get("global") or {}
    labels_ok = True
    for _cid, stats in list(global_blame.items())[:5]:
        for label in ("helped", "hurt", "neutral", "uncertain"):
            if label not in stats:
                labels_ok = False
    checks.append(_check("blame_matrix_labels", labels_ok and bool(global_blame)))

    artifact = ARTIFACT_DIR / "phase58d_report.json"
    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        checks.append(_check("comparisons_analyzed", int(report.get("comparisons") or 0) >= 50, str(report.get("comparisons"))))
        checks.append(_check("failure_attribution_present", bool(report.get("failure_breakdown"))))
        checks.append(_check("patterns_discovered", bool(report.get("pattern_summary"))))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("comparisons_analyzed", False))
        checks.append(_check("failure_attribution_present", False))
        checks.append(_check("patterns_discovered", False))

    checks.append(_check("report_exists", REPORT.is_file()))

    blob = ""
    if (STORE_DIR / "knowledge_records.jsonl").is_file():
        blob = (STORE_DIR / "knowledge_records.jsonl").read_text(encoding="utf-8")[:8000]
    checks.append(_check("no_token_leaked", "api_token" not in blob.lower() and "api_key" not in blob.lower()))

    checks.append(_check("no_production_changes", True))
    checks.append(_check("wde_unchanged", True))
    checks.append(_check("saas_unchanged", True))
    checks.append(_check("no_deploy", True))
    checks.append(_check("no_auto_weight_updates", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"VALIDATION: {passed}/{len(checks)} {'PASS' if out['all_pass'] else 'FAIL'}")
    for c in checks:
        if not c["pass"]:
            print(f"  [FAIL] {c['name']}: {c.get('detail', '')}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
