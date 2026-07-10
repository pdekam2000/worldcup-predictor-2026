#!/usr/bin/env python3
"""Forward evaluation automation status (read-only, no secrets)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.automation import AUTOMATION_ENABLED, SCHEDULE, automation_status
from worldcup_predictor.forward_evaluation.db import connect_eval_db


def _git_sha() -> str | None:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
        return out.strip()
    except Exception:
        return None


def _timer_state(unit: str) -> dict:
    state = {"unit": unit, "active": None, "enabled": None, "next": None}
    try:
        active = subprocess.check_output(["systemctl", "is-active", unit], text=True, stderr=subprocess.DEVNULL).strip()
        state["active"] = active
    except Exception:
        state["active"] = "unknown"
    try:
        enabled = subprocess.check_output(["systemctl", "is-enabled", unit], text=True, stderr=subprocess.DEVNULL).strip()
        state["enabled"] = enabled
    except Exception:
        state["enabled"] = "unknown"
    try:
        out = subprocess.check_output(["systemctl", "list-timers", unit, "--no-pager"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if unit in line:
                parts = line.split()
                if len(parts) >= 2:
                    state["next"] = parts[1] if parts[0] == unit else parts[-1]
                break
    except Exception:
        pass
    return state


def main() -> int:
    conn = connect_eval_db()
    try:
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM frozen_predictions WHERE evaluation_status='PENDING'"
        ).fetchone()["c"]
        evaluated = conn.execute(
            "SELECT COUNT(*) AS c FROM frozen_predictions WHERE evaluation_status='EVALUATED'"
        ).fetchone()["c"]
        frozen_total = conn.execute("SELECT COUNT(*) AS c FROM frozen_predictions").fetchone()["c"]
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        frozen_today = conn.execute(
            "SELECT COUNT(*) AS c FROM frozen_predictions WHERE frozen_at LIKE ?",
            (f"{today}%",),
        ).fetchone()["c"]
        evaluated_today = conn.execute(
            """
            SELECT COUNT(*) AS c FROM frozen_predictions
            WHERE evaluation_status='EVALUATED' AND frozen_at LIKE ?
            """,
            (f"{today}%",),
        ).fetchone()["c"]
        last_batch = conn.execute(
            "SELECT batch_id, created_at, status FROM evaluation_batches ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    timers = [
        _timer_state("worldcup-forward-evaluation-daily.timer"),
        _timer_state("worldcup-forward-evaluation-weekly.timer"),
    ]

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "automation_enabled": AUTOMATION_ENABLED,
        "automation_status": automation_status(),
        "schedule": SCHEDULE,
        "timers": timers,
        "eval_db": {
            "frozen_total": frozen_total,
            "pending_count": pending,
            "evaluated_total": evaluated,
            "frozen_today": frozen_today,
            "evaluated_today": evaluated_today,
        },
        "last_batch": dict(last_batch) if last_batch else None,
        "canonical_git_sha": _git_sha(),
        "last_error_category": None,
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
