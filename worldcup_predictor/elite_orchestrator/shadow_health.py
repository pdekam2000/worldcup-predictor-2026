"""Phase A22 — Elite Shadow scheduler health state."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "shadow" / "elite_shadow_scheduler_state.json"
ARTIFACT_DIR = ROOT / "artifacts" / "phase_a22_shadow_runtime"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "phase": "A22",
        "scheduler_enabled": False,
        "last_run_at": None,
        "last_success_at": None,
        "next_run_estimate": None,
        "last_duration_seconds": None,
        "last_status": "never_run",
        "last_error": None,
        "retry_count": 0,
        "rows_generated_last_run": 0,
        "predictions_written": 0,
        "evaluations_written": 0,
        "root_cause_records_added": 0,
        "queue_pending": 0,
        "last_root_cause_at": None,
        "last_evaluation_at": None,
        "last_cycle_report": None,
    }


def load_health_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return _default_state()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = _default_state()
            base.update(data)
            return base
    except (json.JSONDecodeError, OSError):
        pass
    return _default_state()


def save_health_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "latest_health.json").write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def mark_run_start(*, scheduler_enabled: bool = True) -> dict[str, Any]:
    state = load_health_state()
    state["scheduler_enabled"] = scheduler_enabled
    state["last_run_at"] = _utc_now()
    state["last_status"] = "running"
    state["last_error"] = None
    save_health_state(state)
    return state


def mark_run_success(
    report: dict[str, Any],
    *,
    duration_seconds: float,
    interval_hours: int = 1,
) -> dict[str, Any]:
    state = load_health_state()
    state["last_status"] = "ok"
    state["last_success_at"] = _utc_now()
    state["last_duration_seconds"] = round(duration_seconds, 2)
    state["retry_count"] = 0
    state["rows_generated_last_run"] = int(report.get("predictions_generated") or 0)
    state["predictions_written"] = int((report.get("write_result") or {}).get("written") or 0)
    state["evaluations_written"] = int((report.get("pair_result") or {}).get("evaluations_written") or 0)
    rc = report.get("root_cause") or {}
    state["root_cause_records_added"] = int(rc.get("records_added") or 0)
    if state["evaluations_written"]:
        state["last_evaluation_at"] = _utc_now()
    if state["root_cause_records_added"]:
        state["last_root_cause_at"] = _utc_now()
    state["queue_pending"] = int(report.get("queue_pending") or 0)
    state["last_cycle_report"] = report
    try:
        started = datetime.fromisoformat(str(state.get("last_run_at")))
        state["next_run_estimate"] = (started + timedelta(hours=interval_hours)).isoformat()
    except (TypeError, ValueError):
        state["next_run_estimate"] = None
    save_health_state(state)
    return state


def mark_run_failure(error: str, *, retry_count: int = 0) -> dict[str, Any]:
    state = load_health_state()
    state["last_status"] = "error"
    state["last_error"] = str(error)[:2000]
    state["retry_count"] = retry_count
    save_health_state(state)
    return state


def health_for_api() -> dict[str, Any]:
    from worldcup_predictor.admin.elite_shadow_preview import EliteShadowPreviewService
    from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import count_jsonl_lines
    from worldcup_predictor.elite_orchestrator.shadow_config import EVALUATIONS_PATH, PREDICTIONS_PATH
    from worldcup_predictor.root_cause.config import STORE_DIR

    state = load_health_state()
    summary = EliteShadowPreviewService().preview_summary()
    return {
        "status": "ok",
        "scheduler": state,
        "summary": summary,
        "jsonl_counts": {
            "predictions": count_jsonl_lines(PREDICTIONS_PATH),
            "evaluations": count_jsonl_lines(EVALUATIONS_PATH),
            "root_cause": count_jsonl_lines(STORE_DIR / "knowledge_records.jsonl"),
        },
        "shadow_only": True,
    }
