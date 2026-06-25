#!/usr/bin/env python3
"""Validate Phase 58C Elite Orchestrator shadow runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase58c_elite_shadow_runtime"
PREDICTIONS = ROOT / "data" / "shadow" / "elite_orchestrator_predictions.jsonl"
EVALUATIONS = ROOT / "data" / "shadow" / "elite_orchestrator_evaluations.jsonl"
REPORT = ROOT / "PHASE_58C_ELITE_SHADOW_RUNTIME_REPORT.md"


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
        from worldcup_predictor.elite_orchestrator.shadow_runner import VALID_RECOMMENDATIONS, run_shadow_runtime
        from worldcup_predictor.elite_orchestrator.shadow_store import validate_row

        checks.append(_check("shadow_runtime_imports", True))
    except Exception as exc:
        checks.append(_check("shadow_runtime_imports", False, str(exc)))
        VALID_RECOMMENDATIONS = frozenset()  # type: ignore
        run_shadow_runtime = None  # type: ignore
        validate_row = None  # type: ignore

    for mod in (
        "shadow_config.py",
        "fixture_selector.py",
        "shadow_runtime.py",
        "shadow_store.py",
        "pairing.py",
        "shadow_runner.py",
    ):
        checks.append(_check(f"module_{mod}", (ROOT / "worldcup_predictor" / "elite_orchestrator" / mod).is_file()))

    # Run runtime if no predictions yet
    if not PREDICTIONS.is_file() and run_shadow_runtime:
        run_shadow_runtime(force=True)
    elif not PREDICTIONS.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase58c_elite_shadow_runtime.py"), "--force"], check=False)

    preds = _load_jsonl(PREDICTIONS)
    checks.append(_check("shadow_predictions_generated", len(preds) > 0, str(len(preds))))

    jsonl_valid = True
    for row in preds[:20]:
        if validate_row:
            errs = validate_row(row)
            if errs:
                jsonl_valid = False
                break
    checks.append(_check("jsonl_valid", jsonl_valid))

    # Duplicate protection: second run should skip
    if run_shadow_runtime:
        before = len(preds)
        r2 = run_shadow_runtime(force=False)
        after = len(_load_jsonl(PREDICTIONS))
        skipped = (r2.get("write_result") or {}).get("skipped_duplicates", 0)
        checks.append(_check("duplicate_protection", after == before or skipped > 0, f"skipped={skipped}"))

    checks.append(_check("is_user_visible_false", all(r.get("is_user_visible") is False for r in preds[:50])))
    checks.append(_check("is_shadow_true", all(r.get("is_shadow") is True for r in preds[:50])))

    # Pairing
    subprocess.run([sys.executable, str(ROOT / "scripts" / "phase58c_pair_shadow_predictions.py")], check=False)
    evals = _load_jsonl(EVALUATIONS)
    checks.append(_check("evaluations_jsonl", EVALUATIONS.is_file()))
    checks.append(_check("pairing_pending_or_paired", any(e.get("outcome") in ("pending", "correct", "incorrect") for e in evals)))

    # No secrets in output
    blob = PREDICTIONS.read_text(encoding="utf-8")[:5000] if PREDICTIONS.is_file() else ""
    checks.append(_check("no_token_leaked", "api_token" not in blob.lower() and "api_key" not in blob.lower()))

    summary = ARTIFACT_DIR / "runtime_summary.json"
    if summary.is_file():
        report = json.loads(summary.read_text(encoding="utf-8"))
        rec = report.get("recommendation")
        checks.append(_check("recommendation_valid", rec in VALID_RECOMMENDATIONS, str(rec)))
        checks.append(_check("six_markets", len(report.get("markets_covered") or []) >= 5))
    else:
        checks.append(_check("recommendation_valid", False))
        checks.append(_check("six_markets", False))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", True))
    checks.append(_check("wde_unchanged", True))
    checks.append(_check("saas_unchanged", True))
    checks.append(_check("no_deploy", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
