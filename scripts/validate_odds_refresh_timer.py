#!/usr/bin/env python3
"""Validate odds refresh systemd service and timer configuration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "deployment/systemd/worldcup-odds-refresh.service"
TIMER = ROOT / "deployment/systemd/worldcup-odds-refresh.timer"
SCRIPT = ROOT / "scripts/run_scheduled_odds_refresh.py"


def main() -> int:
    checks: dict[str, bool] = {}
    svc = SERVICE.read_text(encoding="utf-8") if SERVICE.exists() else ""
    tmr = TIMER.read_text(encoding="utf-8") if TIMER.exists() else ""
    scr = SCRIPT.read_text(encoding="utf-8") if SCRIPT.exists() else ""

    checks["service_file_exists"] = SERVICE.exists()
    checks["timer_file_exists"] = TIMER.exists()
    checks["oneshot_service"] = "Type=oneshot" in svc
    checks["odds_script_only"] = "run_scheduled_odds_refresh.py" in svc
    checks["max_calls_20"] = "--max-api-calls 20" in svc
    checks["no_prediction_worker"] = "startPredictionJob" not in svc and "execute_prediction_job" not in svc
    checks["no_wde"] = "run_daily_wde" not in scr
    checks["no_ecse"] = "run_daily_ecse" not in scr
    checks["process_lock"] = "single_instance_lock" in scr
    checks["quota_guard"] = "check_daily_live_budget" in scr
    checks["skip_fresh_in_discovery"] = "FRESH_ODDS" in scr
    checks["post_kickoff_excluded"] = "ko <= now" in scr or "ko is None or ko <= now" in scr
    checks["no_api_key_in_service"] = "API_FOOTBALL" not in svc and "api_key" not in svc.lower()
    checks["timer_30_min"] = "0/30" in tmr
    checks["persistent_timer"] = "Persistent=true" in tmr
    checks["randomized_delay"] = "RandomizedDelaySec" in tmr
    checks["predictions_created_zero"] = "predictions_created" in scr

    passed = all(checks.values())
    print(json.dumps({"passed": passed, "checks": checks}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
