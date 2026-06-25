"""Persist EGIE scheduler run metadata for monitoring dashboard (Phase 51G)."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_STATE_REL = Path("data/egie/scheduler_state.json")


def _state_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    base = Path(settings.sqlite_path).parent if settings.sqlite_path else Path("data")
    if (Path.cwd() / "data").is_dir():
        return Path.cwd() / _STATE_REL
    return base / "egie" / "scheduler_state.json"


def load_scheduler_state(settings: Settings | None = None) -> dict[str, Any]:
    path = _state_path(settings)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read scheduler state %s: %s", path, exc)
        return {}


def save_scheduler_state(payload: dict[str, Any], settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def record_scheduler_run(
    job_payload: dict[str, Any],
    *,
    settings: Settings | None = None,
    source: str = "egie-goal-timing-evaluation",
) -> dict[str, Any]:
    """Write last run summary after evaluation loop completes."""
    settings = settings or get_settings()
    now = datetime.now(timezone.utc).isoformat()
    job = job_payload.get("job") or {}
    refresh = job.get("refresh") or {}
    existing = load_scheduler_state(settings)

    state = {
        **existing,
        "source": source,
        "last_run_at": now,
        "last_refresh_at": now if refresh else existing.get("last_refresh_at"),
        "last_api_calls": int(refresh.get("api_fetches") or 0),
        "last_job": {
            "scanned_picks": job.get("scanned", 0),
            "evaluated": job.get("evaluated", 0),
            "updated": job.get("updated", 0),
            "skipped_not_finished": job.get("skipped_not_finished", 0),
            "skipped_unchanged": job.get("skipped_unchanged", 0),
            "skipped_no_actuals": job.get("skipped_no_actuals", 0),
            "errors": job.get("errors", 0),
        },
        "last_refresh": {
            "scanned": refresh.get("scanned", 0),
            "api_fetches": refresh.get("api_fetches", 0),
            "fixtures_updated": refresh.get("fixtures_updated", 0),
            "results_updated": refresh.get("results_updated", 0),
            "outcomes_persisted": refresh.get("outcomes_persisted", 0),
            "errors": refresh.get("errors", 0),
        },
        "learning_sample_size": (job_payload.get("learning_stats") or {}).get("sample_size", 0),
    }
    save_scheduler_state(state, settings)
    return state


def probe_systemd_timer() -> dict[str, Any]:
    """Best-effort timer probe (production Linux only)."""
    unit = "egie-goal-timing-evaluation.timer"
    out: dict[str, Any] = {
        "timer_unit": unit,
        "timer_installed": False,
        "timer_active": False,
        "next_run_at": None,
    }
    try:
        enabled = subprocess.run(
            ["systemctl", "is-enabled", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        active = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
        )
        out["timer_installed"] = enabled.returncode == 0
        out["timer_active"] = active.returncode == 0 and active.stdout.strip() == "active"

        show = subprocess.run(
            ["systemctl", "show", unit, "--property=NextElapseUSecRealtime"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if show.returncode == 0 and "=" in show.stdout:
            raw = show.stdout.strip().split("=", 1)[1].strip()
            if raw and raw not in {"n/a", "0"}:
                try:
                    ts_us = int(raw)
                    out["next_run_at"] = datetime.fromtimestamp(
                        ts_us / 1_000_000,
                        tz=timezone.utc,
                    ).isoformat()
                except ValueError:
                    out["next_run_at"] = raw
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return out
