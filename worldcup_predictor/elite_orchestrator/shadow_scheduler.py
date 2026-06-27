"""Phase A22 — hourly Elite Shadow scheduler with retry (production-independent)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.elite_orchestrator.autonomous_shadow_cycle import run_autonomous_shadow_cycle
from worldcup_predictor.elite_orchestrator.shadow_health import ARTIFACT_DIR, mark_run_failure

ARTIFACT_PATH = ARTIFACT_DIR / "latest_scheduler_run.json"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30


def run_elite_shadow_scheduler_once(
    *,
    settings: Settings | None = None,
    max_retries: int = MAX_RETRIES,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Single scheduler tick — retries on failure without corrupting JSONL."""
    settings = settings or get_settings()
    last_report: dict[str, Any] = {"status": "error", "error": "no_attempt"}

    for attempt in range(1, max_retries + 1):
        last_report = run_autonomous_shadow_cycle(
            settings=settings,
            dry_run=dry_run,
            force=force,
            trigger="scheduler",
        )
        if last_report.get("status") == "ok":
            ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
            ARTIFACT_PATH.write_text(json.dumps(last_report, indent=2, default=str), encoding="utf-8")
            return last_report

        mark_run_failure(
            str(last_report.get("error") or "cycle_failed"),
            retry_count=attempt,
        )
        if attempt < max_retries:
            time.sleep(RETRY_DELAY_SECONDS)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(last_report, indent=2, default=str), encoding="utf-8")
    return last_report
