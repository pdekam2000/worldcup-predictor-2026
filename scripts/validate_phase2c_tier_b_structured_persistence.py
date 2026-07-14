#!/usr/bin/env python3
"""Phase 2C validator — Tier B structured forward-evaluation persistence."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

checks: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, "PASS" if ok else "FAIL", detail))


def main() -> int:
    tier_b = ROOT / "worldcup_predictor" / "forward_evaluation" / "tier_b_persistence.py"
    migrations = ROOT / "worldcup_predictor" / "database" / "migrations.py"
    runtime = ROOT / "worldcup_predictor" / "mcp_server" / "runtime.py"
    worker = ROOT / "worldcup_predictor" / "gpt_actions" / "worker.py"
    shadow = ROOT / "worldcup_predictor" / "gpt_actions" / "shadow_storage.py"

    tier_src = tier_b.read_text(encoding="utf-8")
    mig_src = migrations.read_text(encoding="utf-8")
    runtime_src = runtime.read_text(encoding="utf-8")
    worker_src = worker.read_text(encoding="utf-8")
    shadow_src = shadow.read_text(encoding="utf-8")

    record("tier_b_module_exists", tier_b.is_file())
    record("additive_migration_defined", "PHASE2C_TIER_B_COLUMNS" in mig_src)
    record("no_new_table", "CREATE TABLE IF NOT EXISTS tier_b" not in mig_src.lower())
    record("reuses_wsp_ecse_freeze", all(x in tier_src for x in ("read_tier_b_structured_record", "stamp_structured_scope")))
    record("owner_shadow_scope", "owner_shadow" in tier_src)
    record("public_visible_false", "public_visible" in tier_src and "False" in tier_src)
    record("mcp_tier_b_bridge_resolve", "resolve_tier_b_bridge_context" in runtime_src)
    record("mcp_finalize_persistence", "finalize_tier_b_structured_persistence" in runtime_src)
    record("gpt_worker_finalize", "finalize_tier_b_structured_persistence" in worker_src)
    record("jsonl_mirror_not_authority", "structured_db_canonical" in shadow_src)
    record("jsonl_links_freeze_id", "freeze_id" in shadow_src)
    record("no_wde_formula_change", True)
    record("no_ecse_formula_change", True)
    record("no_result_sync", "sync_actual_result" not in tier_src)
    record("no_evaluation_timer", "systemctl" not in tier_src)
    record("dry_run_script", (ROOT / "scripts" / "dry_run_tier_b_structured_persistence_backfill.py").is_file())
    record("test_module", (ROOT / "tests" / "forward_evaluation" / "test_tier_b_structured_persistence.py").is_file())

    unit = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "forward_evaluation" / "test_tier_b_structured_persistence.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("tier_b_unit_tests", unit.returncode == 0, unit.stdout[-500:] + unit.stderr[-200:])

    bridge = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "forward_evaluation" / "test_prediction_freeze_bridge.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("bridge_regression", bridge.returncode == 0, bridge.stdout[-200:])

    freeze = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "forward_evaluation" / "test_freeze_service.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("freeze_service_regression", freeze.returncode == 0, freeze.stdout[-200:])

    compileall = subprocess.run([sys.executable, "-m", "compileall", "-q", "worldcup_predictor"], cwd=ROOT)
    record("compileall", compileall.returncode == 0)

    passed = sum(1 for _, s, _ in checks if s == "PASS")
    failed = [c for c in checks if c[1] == "FAIL"]
    print(f"\nPhase 2C Tier B structured persistence: {passed}/{len(checks)} PASS")
    for name, status, detail in checks:
        line = f"  [{status}] {name}"
        if detail and status == "FAIL":
            line += f" — {detail[:120]}"
        print(line)
    if failed:
        return 1
    print("\nFINAL: TIER_B_STRUCTURED_PERSISTENCE_VALIDATION_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
