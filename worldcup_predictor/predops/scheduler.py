"""PredOps scheduler — Phase A15."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.predops.combo_readiness import build_combo_readiness_report
from worldcup_predictor.predops.coverage import build_predops_coverage_report
from worldcup_predictor.predops.engine import run_predops_cycle
from worldcup_predictor.predops.store import PredOpsStore


def _state_path(settings: Settings) -> Path:
    base = Path(settings.sqlite_path or "data").parent
    return base / "shadow" / "predops_scheduler_state.json"


def run_predops_scheduler_once(
    *,
    settings: Settings | None = None,
    window_days: int | None = None,
    max_jobs: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    started = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    cycle = run_predops_cycle(
        settings=settings,
        window_days=window_days,
        max_jobs=max_jobs,
        dry_run=dry_run,
    )
    coverage = build_predops_coverage_report(settings=settings, window_days=window_days or 7)
    combo = build_combo_readiness_report(settings=settings)
    store = PredOpsStore(settings)
    queue_stats = store.queue_stats()

    report = {
        "phase": "A15",
        "started_at": started,
        "ran_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "dry_run": dry_run,
        "cycle": {
            "enqueued": cycle.enqueued,
            "processed": cycle.processed,
            "snapshots_created": cycle.snapshots_created,
            "skipped": cycle.skipped,
            "errors": cycle.errors,
            "elapsed_ms": cycle.elapsed_ms,
            "max_jobs": cycle.max_jobs,
        },
        "queue": queue_stats,
        "coverage": coverage,
        "combo_readiness": combo,
        "scheduler": {
            "last_run": started,
            "next_run_estimate": (
                datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
            ).isoformat(),
            "queue_length": queue_stats.get("queued", 0),
            "avg_generation_ms": round(cycle.elapsed_ms / max(cycle.processed, 1), 1),
        },
    }
    store.save_scheduler_run(report)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
