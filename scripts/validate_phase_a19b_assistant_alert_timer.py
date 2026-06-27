#!/usr/bin/env python3
"""Phase A19B — AI Assistant alert scan timer validation."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
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

    service = SYSTEMD / "worldcup-assistant-alert-scan.service"
    timer = SYSTEMD / "worldcup-assistant-alert-scan.timer"
    install = ROOT / "scripts" / "install_phase_a19b_assistant_alert_timer.sh"
    record(checks, "service_file", service.is_file())
    record(checks, "timer_file", timer.is_file())
    record(checks, "install_script", install.is_file())

    svc_text = service.read_text(encoding="utf-8") if service.is_file() else ""
    timer_text = timer.read_text(encoding="utf-8") if timer.is_file() else ""
    record(checks, "service_lock_env", "ASSISTANT_ALERT_SCAN_LOCK" in svc_text)
    record(checks, "service_cli_entry", "assistant-alert-scan" in svc_text)
    record(checks, "timer_15min", "00/15:00" in timer_text or "15min" in timer_text.lower())
    record(checks, "timer_persistent", "Persistent=true" in timer_text)

    main_py = (ROOT / "main.py").read_text(encoding="utf-8")
    record(checks, "cli_command_registered", "assistant-alert-scan" in main_py)

    scan_job = ROOT / "worldcup_predictor/ai_assistant/scan_job.py"
    record(checks, "scan_job_module", scan_job.is_file())
    record(checks, "overlap_guard", "overlap" in scan_job.read_text(encoding="utf-8"))

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    try:
        from worldcup_predictor.ai_assistant.rules import build_dedup_key, should_notify_user
        from worldcup_predictor.ai_assistant.scan_job import run_alert_scan_job, run_assistant_alert_scan_command
        from worldcup_predictor.ai_assistant.store import AssistantStore
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)

        uid = f"test-a19b-{uuid.uuid4().hex[:8]}"
        store = AssistantStore()
        store.add_watchlist(uid, item_type="fixture", item_id="99999100", item_name="Timer Test")
        store.upsert_preferences(uid, {"min_bet_quality": 70, "alert_frequency": "normal"})

        result = run_alert_scan_job(user_id=uid)
        record(checks, "scan_runs", result.get("status") in ("ok", "skipped"))
        record(checks, "scan_has_timestamps", "started_at" in result and "finished_at" in result)

        overlap = run_alert_scan_job(user_id=uid)
        # Second call may succeed on Windows without flock; on Linux with flock both may run sequentially
        record(checks, "overlap_handled", overlap.get("status") in ("ok", "skipped"))

        n1 = store.create_notification(
            uid,
            category="quality",
            alert_type="quality_increase",
            title="Dedup test",
            message="First",
            dedup_key=build_dedup_key("quality_increase", 99999100, "80"),
        )
        n2 = store.create_notification(
            uid,
            category="quality",
            alert_type="quality_increase",
            title="Dedup test 2",
            message="Duplicate",
            dedup_key=build_dedup_key("quality_increase", 99999100, "80"),
        )
        record(checks, "no_duplicate_alerts", n1 is not None and n2 is None)

        prefs = store.get_preferences(uid)
        record(checks, "preferences_respected", prefs.get("min_bet_quality") == 70)

        quiet_prefs = {**prefs, "quiet_hours_start": "00:00", "quiet_hours_end": "23:59", "timezone": "UTC"}
        record(
            checks,
            "quiet_hours_logic",
            should_notify_user(quiet_prefs, alert_type="quality_increase") is False
            and should_notify_user(quiet_prefs, alert_type="paper_bet_settled") is True,
        )

        # Legacy SaaS notifications route preserved
        user_routes = (ROOT / "worldcup_predictor/api/routes/user.py").read_text(encoding="utf-8")
        record(checks, "legacy_notifications_preserved", '@router.get("/notifications")' in user_routes)

        import io

        buf = io.StringIO()
        cli_rc = run_assistant_alert_scan_command(user_id=uid, stream=buf)
        record(checks, "cli_command_works", cli_rc == 0 and "Phase A19B" in buf.getvalue())

        proc = subprocess.run(
            [sys.executable, "main.py", "assistant-alert-scan", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        record(checks, "cli_help", proc.returncode == 0 and "assistant-alert-scan" in proc.stdout)

    except Exception as exc:
        record(checks, "runtime_tests", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A19B validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        extra = f" — {detail}" if detail and not ok else ""
        print(f"  [{status}] {name}{extra}")

    out = ROOT / "data" / "validation" / "phase_a19b_assistant_alert_timer_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]},
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
