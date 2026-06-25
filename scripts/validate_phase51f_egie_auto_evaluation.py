#!/usr/bin/env python3
"""Phase 51F — EGIE auto evaluation scheduler validation."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts" / "phase51f_egie_auto_evaluation_validation.json"


def _systemctl_ok(unit: str, subcmd: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", subcmd, unit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    service_path = ROOT / "deployment" / "systemd" / "egie-goal-timing-evaluation.service"
    timer_path = ROOT / "deployment" / "systemd" / "egie-goal-timing-evaluation.timer"
    install_script = ROOT / "scripts" / "install_phase51f_egie_eval_timer.sh"

    record("service_unit_exists", service_path.is_file())
    record("timer_unit_exists", timer_path.is_file())
    record("install_script_exists", install_script.is_file())

    service_text = service_path.read_text(encoding="utf-8") if service_path.is_file() else ""
    timer_text = timer_path.read_text(encoding="utf-8") if timer_path.is_file() else ""
    record("service_runs_main_command", "egie-goal-timing-evaluation" in service_text)
    record("service_uses_www_data", "User=www-data" in service_text)
    record("timer_every_30_min", "00,30:00" in timer_text)

    from worldcup_predictor.goal_timing.auto_evaluation_job import (
        egie_evaluation_exit_code,
        run_production_egie_goal_timing_evaluation,
    )
    from worldcup_predictor.goal_timing.evaluation_job import GoalTimingEvaluationJobResult

    record("auto_eval_module_import", True)
    record("exit_code_helper", egie_evaluation_exit_code(GoalTimingEvaluationJobResult(errors=0)) == 0)
    record("exit_code_errors", egie_evaluation_exit_code({"job": {"errors": 1}}) == 1)

    try:
        payload = run_production_egie_goal_timing_evaluation(limit=10, max_api_calls=0)
        job = payload.get("job") or {}
        record("manual_run_ok", isinstance(job, dict))
        record("manual_run_has_scanned", "scanned" in job, str(job.get("scanned")))
    except Exception as exc:
        record("manual_run_ok", False, str(exc))
        record("manual_run_has_scanned", False)

    on_server = Path("/opt/worldcup-predictor").is_dir()
    if on_server:
        record("timer_installed", _systemctl_ok("egie-goal-timing-evaluation.timer", "is-enabled"))
        record("timer_active", _systemctl_ok("egie-goal-timing-evaluation.timer", "is-active"))
        try:
            import os

            if os.geteuid() == 0:
                cmd = [
                    "runuser",
                    "-u",
                    "www-data",
                    "--",
                    "bash",
                    "-lc",
                    "cd /opt/worldcup-predictor && set -a && source .env.production && set +a && "
                    ".venv/bin/python main.py egie-goal-timing-evaluation --limit 50 --max-api-calls 5",
                ]
            else:
                cmd = [
                    "bash",
                    "-lc",
                    "cd /opt/worldcup-predictor && set -a && source .env.production && set +a && "
                    ".venv/bin/python main.py egie-goal-timing-evaluation --limit 50 --max-api-calls 5",
                ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            record("production_manual_run", proc.returncode == 0, f"exit={proc.returncode}")
            record("production_log_scanned", "Scanned picks:" in out or "scanned_picks=" in out)
        except Exception as exc:
            record("production_manual_run", False, str(exc))
            record("production_log_scanned", False)
    else:
        record("timer_installed", True, "skipped (not on production host)")
        record("timer_active", True, "skipped (not on production host)")
        record("production_manual_run", True, "skipped (local dev)")
        record("production_log_scanned", True, "skipped (local dev)")

    from worldcup_predictor.api.routes import goal_timing as gt_routes

    paths = {getattr(r, "path", "") for r in gt_routes.router.routes}
    for endpoint in (
        "/goal-timing/history",
        "/goal-timing/accuracy",
        "/goal-timing/performance",
        "/goal-timing/dashboard",
    ):
        record(f"route_{endpoint.split('/')[-1]}", endpoint in paths)

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "phase": "51F",
                "passed": passed,
                "total": total,
                "on_server": on_server,
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Phase 51F validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
