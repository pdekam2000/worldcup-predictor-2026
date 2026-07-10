"""Phase 7B Part N — Automation schedule design (timers disabled until approval)."""

from __future__ import annotations

AUTOMATION_ENABLED = False

SCHEDULE = {
    "discovery": {
        "enabled": False,
        "cron_hint": "0 7 * * *",
        "timezone": "Europe/Vienna",
        "description": "Morning discovery of Tier A + Tier B owner fixtures",
    },
    "prematch_freeze": {
        "enabled": False,
        "cron_hint": "0 */2 * * *",
        "timezone": "Europe/Vienna",
        "description": "Rolling prematch freeze window (2h) when odds fresh and kickoff not passed",
    },
    "result_sync": {
        "enabled": False,
        "cron_hint": "30 21,23 * * *",
        "timezone": "Europe/Vienna",
        "description": "Post-match result sync after likely FT windows",
    },
    "weekly_report": {
        "enabled": False,
        "cron_hint": "0 8 * * 1",
        "timezone": "Europe/Vienna",
        "description": "Monday morning weekly owner analysis report",
    },
}


def automation_status() -> dict:
    return {
        "automation_enabled": AUTOMATION_ENABLED,
        "timers_disabled_pending_owner_approval": not AUTOMATION_ENABLED,
        "schedule": SCHEDULE,
    }
