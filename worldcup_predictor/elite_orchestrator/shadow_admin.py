"""Phase A22 — Elite Shadow admin maintenance actions (super_admin only)."""

from __future__ import annotations

import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_orchestrator.autonomous_shadow_cycle import run_autonomous_shadow_cycle
from worldcup_predictor.elite_orchestrator.pairing import pair_predictions
from worldcup_predictor.elite_orchestrator.shadow_config import EVALUATIONS_PATH, PREDICTIONS_PATH
from worldcup_predictor.elite_orchestrator.shadow_jsonl_io import rebuild_jsonl_deduped
from worldcup_predictor.elite_orchestrator.shadow_store import duplicate_key
from worldcup_predictor.root_cause.config import STORE_DIR
from worldcup_predictor.root_cause.runner import run_phase58d

ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = ROOT / "artifacts" / "phase_a22_shadow_runtime" / "exports"


def _eval_dedupe(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row.get("fixture_id") or 0),
        str(row.get("market_id") or ""),
        str(row.get("prediction_day") or ""),
    )


def _rc_dedupe(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row.get("fixture_id") or 0),
        str(row.get("market") or row.get("market_id") or ""),
        str(row.get("failure_reason") or ""),
    )


def run_shadow_now(*, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
    return run_autonomous_shadow_cycle(force=force, dry_run=dry_run, trigger="admin_run_now")


def rebuild_jsonl_store() -> dict[str, Any]:
    return {
        "predictions": rebuild_jsonl_deduped(PREDICTIONS_PATH, dedupe_key=duplicate_key),
        "evaluations": rebuild_jsonl_deduped(EVALUATIONS_PATH, dedupe_key=_eval_dedupe),
        "root_cause": rebuild_jsonl_deduped(STORE_DIR / "knowledge_records.jsonl", dedupe_key=_rc_dedupe),
    }


def recalculate_root_cause(*, force_store: bool = False) -> dict[str, Any]:
    return run_phase58d(force_store=force_store)


def re_evaluate_finished_fixtures(*, force: bool = False) -> dict[str, Any]:
    return pair_predictions(force=force)


def vacuum_shadow_store() -> dict[str, Any]:
    return rebuild_jsonl_store()


def export_shadow_jsonl() -> dict[str, Any]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = EXPORT_DIR / f"elite_shadow_export_{ts}.tar.gz"
    files = [
        PREDICTIONS_PATH,
        EVALUATIONS_PATH,
        STORE_DIR / "knowledge_records.jsonl",
    ]
    with tarfile.open(out, "w:gz") as tar:
        for path in files:
            if path.is_file():
                tar.add(path, arcname=path.name)
    return {"status": "ok", "export_path": str(out), "files": [str(p) for p in files if p.is_file()]}


def handle_admin_action(action: str, **kwargs: Any) -> dict[str, Any]:
    actions = {
        "run_now": lambda: run_shadow_now(force=bool(kwargs.get("force")), dry_run=bool(kwargs.get("dry_run"))),
        "rebuild_jsonl": rebuild_jsonl_store,
        "recalculate_root_cause": lambda: recalculate_root_cause(force_store=bool(kwargs.get("force_store"))),
        "re_evaluate": lambda: re_evaluate_finished_fixtures(force=bool(kwargs.get("force"))),
        "vacuum": vacuum_shadow_store,
        "export": export_shadow_jsonl,
    }
    if action not in actions:
        return {"status": "error", "error": f"unknown_action:{action}"}
    result = actions[action]()
    return {"status": "ok", "action": action, "result": result}
