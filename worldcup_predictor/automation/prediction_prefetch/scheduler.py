"""Hourly prefetch scheduler entry — Phase A14."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.automation.prediction_prefetch.coverage import build_coverage_report
from worldcup_predictor.automation.prediction_prefetch.engine import PrefetchCycleResult, run_prefetch_cycle
from worldcup_predictor.config.settings import Settings, get_settings


def _state_path(settings: Settings) -> Path:
    base = Path(settings.sqlite_path or "data").parent
    return base / "shadow" / "prefetch_scheduler_state.json"


def run_prefetch_scheduler_once(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    max_per_cycle: int | None = None,
) -> dict[str, Any]:
    """Systemd/cron entry: one hourly prefetch + coverage snapshot."""
    settings = settings or get_settings()
    cycle = run_prefetch_cycle(settings=settings, window_days=window_days, max_per_cycle=max_per_cycle)
    coverage = build_coverage_report(settings=settings, window_days=window_days or 7)
    report = {
        "phase": "A14",
        "ran_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "cycle": {
            "scanned": cycle.scanned,
            "predicted": cycle.predicted,
            "skipped_fresh": cycle.skipped_fresh,
            "skipped_cap": cycle.skipped_cap,
            "errors": cycle.errors,
            "elapsed_ms": cycle.elapsed_ms,
        },
        "coverage": coverage,
    }
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
