#!/usr/bin/env python3
"""Phase 51G — EGIE monitoring dashboard polish validation."""

from __future__ import annotations

import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JSX = ROOT / "base44-d" / "src" / "pages" / "goalTiming" / "GoalTimingDashboardPage.jsx"
SHELL_JSX = ROOT / "base44-d" / "src" / "components" / "goalTiming" / "GoalTimingPageShell.jsx"
ARTIFACT = ROOT / "artifacts" / "phase51g_dashboard_validation.json"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.goal_timing.dashboard_service import GoalTimingDashboardService
    from worldcup_predictor.goal_timing.scheduler_state import load_scheduler_state, record_scheduler_run
    from worldcup_predictor.api.routes import goal_timing as gt_routes

    dash = GoalTimingDashboardService().build_monitoring_dashboard()
    record("dashboard_service_builds", isinstance(dash, dict))
    record("dashboard_has_counts", "counts" in dash and "published_picks" in dash["counts"])
    record("dashboard_has_accuracy", "accuracy" in dash and "team_winrate_pct" in dash["accuracy"])
    record("dashboard_has_scheduler", "scheduler" in dash)
    record("dashboard_has_no_pick", "no_pick" in dash)
    record("dashboard_has_upcoming", "upcoming_picks" in dash)
    record("dashboard_has_recent_evals", "recent_evaluations" in dash)
    record("dashboard_data_source_live", dash.get("data_source") == "postgresql_sqlite_live")
    record("dashboard_no_mock_flag", "demo" not in json.dumps(dash).lower())

    # Engine unchanged — spot check engine module has no dashboard edits
    engine_path = ROOT / "worldcup_predictor" / "goal_timing" / "engine.py"
    engine_src = engine_path.read_text(encoding="utf-8") if engine_path.is_file() else ""
    record("engine_untouched_no_dashboard", "dashboard_service" not in engine_src)

    paths = {getattr(r, "path", "") for r in gt_routes.router.routes}
    for ep in ("dashboard", "picks", "history", "accuracy", "performance"):
        record(f"route_{ep}", f"/goal-timing/{ep}" in paths)

    # Scheduler state roundtrip
    sample = record_scheduler_run(
        {"job": {"scanned": 49, "evaluated": 1, "refresh": {"api_fetches": 2}}, "learning_stats": {"sample_size": 1}},
        source="validate_phase51g",
    )
    record("scheduler_state_written", bool(sample.get("last_run_at")))
    loaded = load_scheduler_state()
    record("scheduler_state_loaded", loaded.get("last_run_at") == sample.get("last_run_at"))

    # Frontend theme checks
    dash_jsx = DASHBOARD_JSX.read_text(encoding="utf-8") if DASHBOARD_JSX.is_file() else ""
    shell_jsx = SHELL_JSX.read_text(encoding="utf-8") if SHELL_JSX.is_file() else ""
    record("frontend_dashboard_exists", DASHBOARD_JSX.is_file())
    record("frontend_white_theme", "bg-white" in dash_jsx and "bg-white" in shell_jsx)
    record("frontend_emerald_accent", "emerald" in dash_jsx)
    record(
        "frontend_no_fake_data",
        "demo data" not in dash_jsx.lower() or "no demo data" in dash_jsx.lower(),
    )
    record("frontend_fetches_real_apis", "fetchGoalTimingDashboard" in dash_jsx)
    record("frontend_error_state", "apiHealth" in dash_jsx and "AlertCircle" in dash_jsx)
    record("frontend_scheduler_visible", "scheduler" in dash_jsx.lower() and "egie-goal-timing" in dash_jsx.lower())
    record("frontend_mobile_grid", bool(re.search(r"grid-cols-2|sm:grid-cols|lg:grid-cols", dash_jsx)))

    on_server = Path("/opt/worldcup-predictor").is_dir()
    if on_server:
        import urllib.request

        for path in (
            "/api/goal-timing/dashboard",
            "/api/goal-timing/picks",
            "/api/goal-timing/history",
            "/api/goal-timing/accuracy",
            "/api/goal-timing/performance",
        ):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=15) as resp:
                    record(f"prod_api_{path.split('/')[-1]}_200", resp.status == 200)
            except Exception as exc:
                record(f"prod_api_{path.split('/')[-1]}_200", False, str(exc))

        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "egie-goal-timing-evaluation.timer"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            record("prod_timer_active", proc.stdout.strip() == "active")
        except Exception as exc:
            record("prod_timer_active", False, str(exc))

        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/goal-timing/dashboard", timeout=15) as resp:
                payload = json.loads(resp.read().decode())
            pub = (payload.get("counts") or {}).get("published_picks", 0)
            ev = (payload.get("counts") or {}).get("evaluated_picks", 0)
            record("prod_real_counts_present", pub >= 1, f"published={pub} evaluated={ev}")
        except Exception as exc:
            record("prod_real_counts_present", False, str(exc))
    else:
        record("prod_api_skipped", True, "local dev")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(
        json.dumps(
            {
                "phase": "51G",
                "passed": passed,
                "total": total,
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Phase 51G validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
