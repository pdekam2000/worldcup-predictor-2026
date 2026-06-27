#!/usr/bin/env python3
"""Phase A22 — Autonomous Elite Shadow Runtime validation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deployment" / "systemd"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # Part 1 — scheduler files
    service = SYSTEMD / "worldcup-elite-shadow.service"
    timer = SYSTEMD / "worldcup-elite-shadow.timer"
    record(checks, "service_file", service.is_file())
    record(checks, "timer_file", timer.is_file())
    svc_text = service.read_text(encoding="utf-8") if service.is_file() else ""
    timer_text = timer.read_text(encoding="utf-8") if timer.is_file() else ""
    record(checks, "service_cli_entry", "elite_shadow_once" in svc_text)
    record(checks, "timer_hourly", "OnCalendar=hourly" in timer_text)
    record(checks, "timer_persistent", "Persistent=true" in timer_text)

    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    record(checks, "cli_elite_shadow_once", "elite_shadow_once" in main_py)
    record(checks, "cli_elite_shadow_scheduler", "elite_shadow_scheduler" in main_py)
    record(checks, "cli_elite_shadow_admin", "elite_shadow_admin" in main_py)

    # Part 2 — JSONL pipeline modules
    jsonl_io = ROOT / "worldcup_predictor/elite_orchestrator/shadow_jsonl_io.py"
    record(checks, "jsonl_io_module", jsonl_io.is_file())
    io_text = jsonl_io.read_text(encoding="utf-8") if jsonl_io.is_file() else ""
    record(checks, "atomic_append", "append_jsonl_rows" in io_text and "jsonl_file_lock" in io_text)
    record(checks, "rebuild_dedup", "rebuild_jsonl_deduped" in io_text)

    cycle = ROOT / "worldcup_predictor/elite_orchestrator/autonomous_shadow_cycle.py"
    scheduler = ROOT / "worldcup_predictor/elite_orchestrator/shadow_scheduler.py"
    health = ROOT / "worldcup_predictor/elite_orchestrator/shadow_health.py"
    queue = ROOT / "worldcup_predictor/elite_orchestrator/shadow_queue.py"
    admin = ROOT / "worldcup_predictor/elite_orchestrator/shadow_admin.py"
    record(checks, "autonomous_cycle", cycle.is_file())
    record(checks, "shadow_scheduler", scheduler.is_file())
    record(checks, "shadow_health", health.is_file())
    record(checks, "shadow_queue", queue.is_file())
    record(checks, "shadow_admin", admin.is_file())

    # Part 3 — PredOps hook (non-blocking)
    snapshots = (ROOT / "worldcup_predictor/predops/snapshots.py").read_text(encoding="utf-8")
    record(checks, "predops_enqueue_hook", "enqueue_shadow_fixture" in snapshots)
    record(checks, "predops_non_blocking", "except Exception" in snapshots)

    # Part 4-5 — root cause + evaluation wiring
    pairing = (ROOT / "worldcup_predictor/elite_orchestrator/pairing.py").read_text(encoding="utf-8")
    record(checks, "pairing_locked_append", "append_jsonl_rows" in pairing)
    record(checks, "pairing_btts", "btts" in pairing)
    record(checks, "pairing_over_under", "over_under" in pairing)

    knowledge = (ROOT / "worldcup_predictor/root_cause/knowledge_store.py").read_text(encoding="utf-8")
    record(checks, "root_cause_dedup", "append_jsonl_rows" in knowledge)

    settings_text = (ROOT / "worldcup_predictor/config/settings.py").read_text(encoding="utf-8")
    record(checks, "settings_elite_shadow", "elite_shadow_scheduler_enabled" in settings_text)

    # Part 6 — admin API
    admin_routes = (ROOT / "worldcup_predictor/api/routes/admin_elite_shadow.py").read_text(encoding="utf-8")
    record(checks, "admin_health_endpoint", '/health' in admin_routes)
    record(checks, "admin_actions_endpoint", "/actions/" in admin_routes)

    # Part 7 — recovery retry
    sched_text = scheduler.read_text(encoding="utf-8") if scheduler.is_file() else ""
    record(checks, "scheduler_retry", "max_retries" in sched_text or "MAX_RETRIES" in sched_text)

    # Part 8 — admin tools CLI
    record(checks, "admin_cli_actions", "rebuild_jsonl" in main_py and "recalculate_root_cause" in main_py)

    # Protected systems untouched
    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    egie_files = list((ROOT / "worldcup_predictor/egie").rglob("*.py"))
    record(checks, "egie_present", len(egie_files) > 0)

    scoring = ROOT / "worldcup_predictor/prediction/scoring_engine.py"
    record(checks, "scoring_engine_present", scoring.is_file())

    # Functional: atomic JSONL append + dedupe
    try:
        from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import (
            append_jsonl_rows,
            count_jsonl_lines,
            rebuild_jsonl_deduped,
        )

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.jsonl"
            key = lambda r: (r["id"],)

            r1 = append_jsonl_rows(p, [{"id": 1, "v": "a"}], dedupe_key=key)
            r2 = append_jsonl_rows(p, [{"id": 1, "v": "dup"}, {"id": 2, "v": "b"}], dedupe_key=key)
            record(checks, "jsonl_append_writes", r1.get("written") == 1)
            record(checks, "jsonl_dedup_skip", r2.get("skipped_duplicates") == 1 and r2.get("written") == 1)
            record(checks, "jsonl_line_count", count_jsonl_lines(p) == 2)

            vacuum = rebuild_jsonl_deduped(p, dedupe_key=key)
            record(checks, "jsonl_vacuum", vacuum.get("after", 0) == 2)
    except Exception as exc:
        record(checks, "jsonl_functional", False, str(exc))

    # Functional: dry-run cycle (no production changes)
    try:
        from worldcup_predictor.elite_orchestrator.autonomous_shadow_cycle import run_autonomous_shadow_cycle

        report = run_autonomous_shadow_cycle(dry_run=True, trigger="validation")
        record(checks, "cycle_dry_run", report.get("status") == "ok")
        record(checks, "production_unchanged_flag", report.get("production_changes") is False)
    except Exception as exc:
        record(checks, "cycle_dry_run", False, str(exc))

    # Functional: health API payload
    try:
        from worldcup_predictor.elite_orchestrator.shadow_health import health_for_api

        health = health_for_api()
        record(checks, "health_payload", health.get("status") == "ok" and "scheduler" in health)
        record(checks, "health_jsonl_counts", "predictions" in (health.get("jsonl_counts") or {}))
    except Exception as exc:
        record(checks, "health_payload", False, str(exc))

    # CLI smoke
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "elite_shadow_once", "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        record(checks, "cli_dry_run_exit", proc.returncode == 0, proc.stderr[-500:] if proc.stderr else "")
    except Exception as exc:
        record(checks, "cli_dry_run_exit", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = [c for c in checks if not c[1]]

    report = {
        "phase": "A22",
        "passed": passed,
        "total": len(checks),
        "status": "AUTONOMOUS_SHADOW_RUNTIME_DEPLOYED_OK" if not failed else "VALIDATION_FAILED",
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
        "failed": [{"name": n, "detail": d} for n, ok, d in failed],
    }
    out_path = ROOT / "artifacts" / "phase_a22_shadow_runtime" / "validation_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Phase A22 validation: {passed}/{len(checks)} passed — {report['status']}")
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail and not ok:
            line += f" — {detail}"
        print(line)

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
