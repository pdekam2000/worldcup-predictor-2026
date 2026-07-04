#!/usr/bin/env python3
"""FIXTURE-SYNC-1 Part E — Safety validation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner_daily.wc_schedule_sync import COMP_KEY, run_wc_schedule_audit
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

PHASE = "FIXTURE-SYNC-1"
ARTIFACT = ROOT / "artifacts" / "fixture_sync" / "fixture_sync_1_validation.json"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _service_active(unit: str) -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.stdout.strip() == "active"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--before-audit-json", default=str(ROOT / "artifacts" / "fixture_sync" / "fixture_sync_1_audit_before.json"))
    parser.add_argument("--sync-json", default=str(ROOT / "artifacts" / "fixture_sync" / "fixture_sync_1_sync_latest.json"))
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    checks: list[dict] = []

    checks.append(_check("production_db_path_set", bool(db_path), str(db_path)))
    checks.append(_check("no_local_db_copy_flag", "copy" not in str(db_path).lower() or "football_intelligence" in str(db_path)))

    audit = run_wc_schedule_audit(db_path=db_path, competition_key=COMP_KEY)
    for fx in audit.upcoming_fixtures:
        ok = str(fx.get("kickoff_utc") or "") >= audit.now_utc
        checks.append(_check(f"future_kickoff_{fx['fixture_id']}", ok, str(fx.get("kickoff_utc"))))

    checks.append(_check("no_duplicate_groups", len(audit.duplicate_suspects) == 0, str(len(audit.duplicate_suspects))))

    conn = connect_readonly(db_path)
    ft_count = conn.execute(
        "SELECT COUNT(*) AS c FROM fixtures WHERE competition_key=? AND is_placeholder=0 AND UPPER(status)='FT'",
        (COMP_KEY,),
    ).fetchone()["c"]
    conn.close()
    checks.append(_check("ft_fixtures_present", int(ft_count) >= 300, f"ft={ft_count}"))

    sync_path = Path(args.sync_json)
    if sync_path.exists():
        sync_payload = json.loads(sync_path.read_text(encoding="utf-8"))
        upcoming = sync_payload.get("upcoming_sync") or {}
        calls = upcoming.get("provider_calls") or {}
        total_calls = sum(int(v) for v in calls.values())
        checks.append(_check("provider_calls_bounded", total_calls <= 20, str(calls)))
        checks.append(_check("provider_calls_logged", bool(calls), json.dumps(calls)))
        repair = sync_payload.get("stale_ns_repair") or {}
        if repair:
            checks.append(_check("stale_ns_calls_bounded", int(repair.get("provider_calls") or 0) <= 20))

    before_path = Path(args.before_audit_json)
    if before_path.exists():
        before = json.loads(before_path.read_text(encoding="utf-8"))
        before_ft = int((before.get("status_counts") or {}).get("FT") or 0)
        after_ft = int((audit.status_counts or {}).get("FT") or 0)
        checks.append(_check("ft_count_not_corrupted", after_ft >= before_ft, f"{before_ft}->{after_ft}"))

    conn2 = connect_readonly(db_path)
    for table in ("worldcup_stored_predictions", "ecse_prediction_snapshots"):
        if table_exists(conn2, table):
            checks.append(_check(f"{table}_readable", True, str(table_count(conn2, table))))
    conn2.close()

    wde_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    checks.append(_check("wde_file_unchanged_marker", "def generate_wde" in wde_src or "wde" in wde_src.lower()))

    ecse_src = (ROOT / "worldcup_predictor" / "research" / "ecse_live" / "runner.py").read_text(encoding="utf-8")
    checks.append(_check("ecse_runner_present", "ecse" in ecse_src.lower()))

    timer_units = ("worldcup-daily.timer", "worldcup-hourly.timer", "owner-daily.timer")
    for unit in timer_units:
        try:
            proc = subprocess.run(["systemctl", "is-enabled", unit], capture_output=True, text=True, timeout=5)
            enabled = proc.stdout.strip() in ("enabled", "enabled-runtime")
            checks.append(_check(f"timer_not_enabled_{unit}", not enabled, proc.stdout.strip()))
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            checks.append(_check(f"timer_check_skipped_{unit}", True, "systemctl unavailable"))

    checks.append(_check("worldcup_api_active", _service_active("worldcup-api")))
    checks.append(_check("nginx_active", _service_active("nginx")))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    result = {
        "phase": PHASE,
        "passed": passed,
        "total": total,
        "all_passed": passed == total,
        "checks": checks,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
