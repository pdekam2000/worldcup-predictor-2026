"""Forward evaluation automation schedule — enabled after activation gate."""

from __future__ import annotations

AUTOMATION_ENABLED = True

# Cadence (Europe/Vienna reporting context; systemd timers use same timezone)
# - Full orchestrator cycle: 07:00 and 17:00 daily (discovery, freeze, sync, evaluate)
# - Weekly report: Monday 08:00
SCHEDULE = {
    "orchestrator_cycle": {
        "enabled": True,
        "cron_hint": "0 7,17 * * *",
        "timezone": "Europe/Vienna",
        "utc_equivalent_hint": "05:00 and 15:00 UTC (CEST)",
        "description": "Unified A+B cycle — discover, classify, freeze, sync, evaluate",
    },
    "weekly_report": {
        "enabled": True,
        "cron_hint": "0 8 * * 1",
        "timezone": "Europe/Vienna",
        "description": "Monday weekly owner analysis report",
    },
}


def automation_status() -> dict:
    return {
        "automation_enabled": AUTOMATION_ENABLED,
        "timers_disabled_pending_owner_approval": not AUTOMATION_ENABLED,
        "schedule": SCHEDULE,
    }
