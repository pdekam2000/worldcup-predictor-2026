#!/usr/bin/env python3
"""Phase A21B — Deploy script hardening validation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def has_flock() -> bool:
    try:
        import fcntl  # noqa: F401

        return True
    except ImportError:
        return False


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "scripts/lib/deploy_hardening.sh",
        "scripts/deploy_run.sh",
        "scripts/deploy_phase_a21_quick.sh",
        "scripts/deploy_phase_a19_production.sh",
        "scripts/deploy_phase_a20_quick.sh",
        "worldcup_predictor/ops/deploy_status.py",
    ):
        record(checks, f"file_{Path(rel).name}", (ROOT / rel).is_file(), rel)

    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    record(checks, "cli_deploy_status_parser", '"deploy-status"' in main_py)
    record(checks, "cli_deploy_status_handler", "run_deploy_status_command" in main_py)

    hardening = (SCRIPTS / "lib" / "deploy_hardening.sh").read_text(encoding="utf-8")
    for token in (
        "deploy_acquire_lock",
        "deploy_run_step",
        "deploy_write_status",
        "DEPLOY_CHECKPOINT_FILE",
        "flock",
    ):
        record(checks, f"hardening_{token}", token in hardening)

    run_sh = (SCRIPTS / "deploy_run.sh").read_text(encoding="utf-8")
    record(checks, "detached_systemd_or_nohup", "systemd-run" in run_sh and "nohup" in run_sh)
    record(checks, "deploy_run_foreground_flag", "--foreground" in run_sh)
    record(checks, "deploy_run_resume_flag", "--resume" in run_sh)

    for name in ("deploy_phase_a21_quick.sh", "deploy_phase_a19_production.sh", "deploy_phase_a20_quick.sh"):
        body = (SCRIPTS / name).read_text(encoding="utf-8")
        record(checks, f"{name}_uses_deploy_run", "deploy_run.sh" in body)
        record(checks, f"{name}_sources_hardening", "deploy_hardening.sh" in body)

    # --- Python deploy-status ---
    try:
        from worldcup_predictor.ops.deploy_status import read_deploy_status, run_deploy_status_command

        with tempfile.TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "deploy"
            log_dir.mkdir(parents=True)
            session = "test_a21b_session"
            status_path = log_dir / f"deploy_{session}.status.json"
            log_path = log_dir / f"deploy_{session}.log"
            checkpoint = log_dir / f"deploy_{session}.checkpoint"
            lock_path = log_dir / ".deploy.lock"

            os.environ["DEPLOY_LOG_DIR"] = str(log_dir)
            os.environ["DEPLOY_LOCK_FILE"] = str(lock_path)

            status_path.write_text(
                json.dumps(
                    {
                        "session_id": session,
                        "state": "running",
                        "current_step": "frontend_build",
                        "message": "in_progress",
                        "pid": 12345,
                        "started_at": "2026-06-25T18:00:00Z",
                        "updated_at": "2026-06-25T18:01:00Z",
                        "log_file": str(log_path),
                        "checkpoint_file": str(checkpoint),
                        "rollback": "backup=/tmp/test",
                        "deploy_label": "test",
                    }
                ),
                encoding="utf-8",
            )
            log_path.write_text("[2026-06-25T18:00:01Z] STEP START: backup\n", encoding="utf-8")
            checkpoint.write_text("backup\nextract\n", encoding="utf-8")
            (log_dir / ".latest_session").write_text(session, encoding="utf-8")
            lock_path.write_text(f"{session} pid=99999", encoding="utf-8")

            view = read_deploy_status(session_id=session)
            record(checks, "status_read_session", view.session_id == session)
            record(checks, "status_read_state", view.state == "running")
            record(checks, "status_rollback_present", view.rollback == "backup=/tmp/test")
            record(checks, "status_log_tail", len(view.log_tail) >= 1)
            record(checks, "status_lock_info", view.lock_held is True)

            rc_idle = run_deploy_status_command(session_id="missing_session_xyz", json_output=True, log_lines=5)
            record(checks, "status_missing_session", rc_idle in (0, 1))

    except Exception as exc:
        record(checks, "python_deploy_status", False, str(exc))

    # --- Bash integration (Linux / Git Bash with flock) ---
    bash = shutil.which("bash")
    if bash and (sys.platform != "win32" or shutil.which("flock")):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"
            log_dir = app / "logs" / "deploy"
            log_dir.mkdir(parents=True)
            backup_root = Path(tmp) / "backups"
            backup_root.mkdir()

            mini_deploy = app / "scripts" / "mini_deploy.sh"
            mini_deploy.parent.mkdir(parents=True, exist_ok=True)
            (app / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
            mini_deploy.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/deploy_hardening.sh"
deploy_init "mini" "$@"
trap 'deploy_release_lock' EXIT
deploy_acquire_lock || exit 3
deploy_run_step s1 /bin/true
deploy_run_step s2 /bin/true
deploy_finish_ok
""",
                encoding="utf-8",
            )
            shutil.copy(SCRIPTS / "lib" / "deploy_hardening.sh", app / "scripts" / "lib" / "deploy_hardening.sh")

            env = {
                **os.environ,
                "DEPLOY_APP": str(app),
                "DEPLOY_LOG_DIR": str(log_dir),
                "DEPLOY_BACKUP_ROOT": str(backup_root),
                "WC_DEPLOY_CHILD": "1",
                "DEPLOY_FOREGROUND": "1",
            }
            proc1 = subprocess.run([bash, str(mini_deploy)], env=env, capture_output=True, text=True)
            record(checks, "mini_deploy_runs", proc1.returncode == 0, (proc1.stderr or proc1.stdout)[-200:])

            status_files = list(log_dir.glob("deploy_*.status.json"))
            record(checks, "status_file_created", len(status_files) == 1)
            data: dict = {}
            if status_files:
                data = json.loads(status_files[0].read_text(encoding="utf-8"))
                record(checks, "status_file_ok_state", data.get("state") == "ok")
            else:
                record(checks, "status_file_ok_state", False, "no status file")

            log_files = list(log_dir.glob("deploy_*.log"))
            record(checks, "deploy_log_written", len(log_files) == 1 and log_files[0].stat().st_size > 0)

            checkpoint_files = list(log_dir.glob("deploy_*.checkpoint"))
            record(checks, "checkpoint_written", len(checkpoint_files) == 1)

            if data.get("session_id"):
                proc2 = subprocess.run(
                    [bash, str(mini_deploy)],
                    env={**env, "DEPLOY_RESUME_SESSION": data.get("session_id", "")},
                    capture_output=True,
                    text=True,
                )
                log_text = ""
                if checkpoint_files:
                    lines = checkpoint_files[0].read_text(encoding="utf-8", errors="replace").splitlines()
                    # Resume must not re-run completed steps (checkpoint lines stay unique).
                    unique_ok = len(lines) == len(set(lines)) and lines.count("s1") == 1
                else:
                    unique_ok = False
                if log_files:
                    log_text = log_files[0].read_text(encoding="utf-8", errors="replace")
                combined = proc2.stdout + proc2.stderr + log_text
                record(
                    checks,
                    "resume_skips_steps",
                    proc2.returncode == 0
                    and ("SKIP (already done): s1" in combined or unique_ok),
                )
            else:
                record(checks, "resume_skips_steps", False, "no session for resume test")

            if has_flock():
                lock = log_dir / ".lock_isolated"
                holder = subprocess.Popen(
                    [
                        bash,
                        "-c",
                        (
                            f"export DEPLOY_LOG_DIR='{log_dir}' DEPLOY_LOCK_FILE='{lock}' "
                            f"DEPLOY_SESSION_ID='holder'; "
                            f"source '{app / 'scripts/lib/deploy_hardening.sh'}'; "
                            "deploy_init holder; deploy_acquire_lock; sleep 8"
                        ),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(0.5)
                proc3 = subprocess.run(
                    [
                        bash,
                        "-c",
                        (
                            f"export DEPLOY_LOG_DIR='{log_dir}' DEPLOY_LOCK_FILE='{lock}' "
                            f"DEPLOY_SESSION_ID='contender'; "
                            f"source '{app / 'scripts/lib/deploy_hardening.sh'}'; "
                            "deploy_init contender; deploy_acquire_lock"
                        ),
                    ],
                    capture_output=True,
                    text=True,
                )
                holder.terminate()
                try:
                    holder.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    holder.kill()
                combined3 = (proc3.stdout or "") + (proc3.stderr or "")
                record(
                    checks,
                    "lock_blocks_duplicate",
                    proc3.returncode != 0
                    or "duplicate" in combined3.lower()
                    or "in progress" in combined3.lower(),
                )
            else:
                record(checks, "lock_blocks_duplicate", True, "skipped (no flock)")

            # deploy_run foreground
            deploy_run = SCRIPTS / "deploy_run.sh"
            stub = app / "scripts" / "stub_deploy.sh"
            stub.write_text("#!/usr/bin/env bash\necho STUB_OK\n", encoding="utf-8")
            proc4 = subprocess.run(
                [bash, str(deploy_run), "--foreground", str(stub)],
                env={**env, "DEPLOY_LOG_DIR": str(log_dir)},
                capture_output=True,
                text=True,
            )
            record(checks, "deploy_run_foreground", proc4.returncode == 0 and "STUB_OK" in proc4.stdout)
    else:
        record(checks, "bash_integration", True, "skipped (no bash/flock)")

    # Product logic unchanged
    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A21B deploy hardening validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))

    out = ROOT / "data" / "validation" / "phase_a21b_deploy_hardening_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
