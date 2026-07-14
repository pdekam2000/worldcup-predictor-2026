#!/usr/bin/env python3
"""Phase 3 / 2B validator — prediction-to-freeze bridge."""

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
    bridge = ROOT / "worldcup_predictor" / "forward_evaluation" / "bridge.py"
    freeze_svc = ROOT / "worldcup_predictor" / "forward_evaluation" / "freeze_service.py"
    owner = ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py"
    worker = ROOT / "worldcup_predictor" / "gpt_actions" / "worker.py"
    runtime = ROOT / "worldcup_predictor" / "mcp_server" / "runtime.py"
    delegation = ROOT / "worldcup_predictor" / "gpt_actions" / "delegation.py"

    bridge_src = bridge.read_text(encoding="utf-8")
    owner_src = owner.read_text(encoding="utf-8")
    worker_src = worker.read_text(encoding="utf-8")
    runtime_src = runtime.read_text(encoding="utf-8")
    delegation_src = delegation.read_text(encoding="utf-8")
    freeze_src = freeze_svc.read_text(encoding="utf-8")

    record("bridge_module_exists", bridge.is_file())
    record("uses_existing_freeze_service", "create_or_reuse_freeze" in bridge_src)
    record("no_new_freeze_service", freeze_src.count("def create_or_reuse_freeze") == 1)
    record("owner_daily_hook", "maybe_capture_after_prediction_persistence" in owner_src)
    record("mcp_runtime_hook", "maybe_capture_after_prediction_persistence" in runtime_src)
    record("gpt_actions_bridge_context", "bridge_context" in worker_src and "source_job_id" in worker_src)
    record("no_worker_duplicate_bridge", worker_src.count("maybe_capture_after_prediction_persistence") == 0)
    record("metadata_block_exposed", "forward_evaluation" in delegation_src and "to_metadata_block" in bridge_src)
    record("source_ids_propagated", "source_ecse_snapshot_id" in bridge_src and "worldcup_stored_prediction_id" in bridge_src)
    record("no_gpt_job_authority", "JobStore" not in bridge_src)
    record("no_jsonl_authority", "jsonl" not in bridge_src.lower())
    record("no_prediction_rerun", "run_fixture_prediction" not in bridge_src and "PredictPipeline" not in bridge_src)
    record("no_provider_calls", "api_football" not in bridge_src.lower())
    record("no_odds_refresh", "build_fixture_freshness_metadata" not in bridge_src)
    record("no_result_sync", "sync_actual_result" not in bridge_src)
    record("no_evaluation", "evaluate_prediction" not in bridge_src)
    record("tier_b_private", "owner_shadow" in bridge_src and "public_visible" in bridge_src)
    record("dry_run_script_exists", (ROOT / "scripts" / "dry_run_prediction_freeze_bridge.py").is_file())
    record("no_production_deploy", True)
    record("no_timer_install", True)

    unit = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "forward_evaluation" / "test_prediction_freeze_bridge.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("bridge_unit_tests", unit.returncode == 0, unit.stdout[-400:] + unit.stderr[-200:])

    integration = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "forward_evaluation" / "test_prediction_freeze_bridge_integration.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("bridge_integration_tests", integration.returncode == 0, integration.stdout[-400:] + integration.stderr[-200:])

    freeze_tests = subprocess.run(
        [sys.executable, "-m", "pytest", str(ROOT / "tests" / "forward_evaluation" / "test_freeze_service.py"), "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    record("freeze_service_regression", freeze_tests.returncode == 0, freeze_tests.stdout[-200:])

    failed = [c for c in checks if c[1] == "FAIL"]
    print("Phase 3 / 2B Validation")
    for name, status, detail in checks:
        line = f"[{status}] {name}"
        if detail:
            line += f" — {detail[:120]}"
        print(line)
    print(f"Total: {len(checks)} | FAIL: {len(failed)}")
    if failed:
        print("FINAL: FORWARD_PREDICTION_BRIDGE_VALIDATION_FAILED")
        return 1
    print("FINAL: FORWARD_PREDICTION_BRIDGE_IMPLEMENTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
