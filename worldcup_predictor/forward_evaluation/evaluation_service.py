"""Phase 2D — Controlled forward market evaluation facade."""

from __future__ import annotations

import sqlite3
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.constants import EVAL_COMPLETE
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.evaluate import evaluate_frozen_prediction as _evaluate_markets
from worldcup_predictor.forward_evaluation.freeze_integrity import verify_freeze_integrity
from worldcup_predictor.forward_evaluation.result_record import (
    ELIGIBILITY_INVALID_FREEZE,
    ELIGIBILITY_OWNER_ONLY,
    ELIGIBILITY_PUBLIC,
    ELIGIBILITY_QUARANTINED,
)
from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture


def _resolve_freeze_id(
    eval_conn: sqlite3.Connection,
    fixture_id: int,
    freeze_id: str | None,
) -> str | None:
    if freeze_id:
        return str(freeze_id)
    row = eval_conn.execute(
        """
        SELECT prediction_id FROM frozen_predictions
        WHERE fixture_id=? AND freeze_status='ACTIVE'
        ORDER BY frozen_at DESC LIMIT 1
        """,
        (int(fixture_id),),
    ).fetchone()
    return str(row["prediction_id"]) if row else None


def _eligibility_class(frozen: dict[str, Any]) -> str:
    scope = str(frozen.get("prediction_scope") or "production")
    if frozen.get("quarantine_reason"):
        return ELIGIBILITY_QUARANTINED
    if int(frozen.get("public_visible") or 0) == 0 or scope in ("owner_shadow", "owner_daily"):
        return ELIGIBILITY_OWNER_ONLY
    return ELIGIBILITY_PUBLIC


def evaluate_frozen_prediction(
    fixture_id: int,
    *,
    freeze_id: str | None = None,
    dry_run: bool = False,
    prod_conn: sqlite3.Connection | None = None,
    eval_conn: sqlite3.Connection | None = None,
    skip_result_sync: bool = False,
) -> dict[str, Any]:
    """Canonical controlled evaluation: result sync → integrity → market evaluation."""
    settings = get_settings()
    own_prod = prod_conn is None
    own_eval = eval_conn is None
    prod = prod_conn or connect(settings.sqlite_path)
    ev = eval_conn or connect_eval_db(project_root())
    fid = int(fixture_id)

    try:
        pid = _resolve_freeze_id(ev, fid, freeze_id)
        if not pid:
            return {
                "evaluated": False,
                "fixture_id": fid,
                "reason": "FREEZE_MISSING",
                "eligibility_class": ELIGIBILITY_INVALID_FREEZE,
            }

        frozen_row = ev.execute(
            "SELECT * FROM frozen_predictions WHERE prediction_id=?",
            (pid,),
        ).fetchone()
        if not frozen_row:
            return {"evaluated": False, "fixture_id": fid, "reason": "FREEZE_MISSING"}
        frozen = dict(frozen_row)

        integrity = verify_freeze_integrity(ev, prod, prediction_id=pid)
        if not integrity.get("ok"):
            return {
                "evaluated": False,
                "fixture_id": fid,
                "freeze_id": pid,
                "reason": integrity.get("reason_code"),
                "eligibility_class": ELIGIBILITY_INVALID_FREEZE,
                "integrity": integrity,
            }

        if not skip_result_sync:
            sync = sync_result_for_fixture(
                fid,
                prod_conn=prod,
                eval_conn=ev,
                settings=settings,
                dry_run=dry_run,
                allow_provider_fetch=not dry_run,
            )
            if not sync.get("result_available") and not dry_run:
                return {
                    "evaluated": False,
                    "fixture_id": fid,
                    "freeze_id": pid,
                    "reason": sync.get("reason") or "result_pending",
                    "result_sync": sync,
                }
        else:
            sync = {"skipped": True}

        if dry_run:
            return {
                "evaluated": False,
                "dry_run": True,
                "fixture_id": fid,
                "freeze_id": pid,
                "prediction_scope": frozen.get("prediction_scope"),
                "content_hash": frozen.get("content_hash"),
                "eligibility_class": _eligibility_class(frozen),
                "integrity": integrity,
                "result_sync": sync,
                "would_evaluate": True,
            }

        outcome = _evaluate_markets(ev, prediction_id=pid, prod_conn=prod)
        if outcome.get("evaluated"):
            eligibility = _eligibility_class(frozen)
            ev.execute(
                """
                UPDATE market_evaluations SET
                    prediction_scope=?,
                    validation_tier=?,
                    content_hash=?,
                    result_content_hash=?,
                    evaluation_version=?,
                    evaluator_source=?,
                    eligibility_class=?,
                    quarantine_status=?
                WHERE prediction_id=?
                """,
                (
                    frozen.get("prediction_scope"),
                    frozen.get("validation_tier"),
                    frozen.get("content_hash"),
                    sync.get("result_content_hash") if isinstance(sync, dict) else None,
                    outcome.get("evaluation_version"),
                    "forward_evaluation.evaluate",
                    eligibility,
                    frozen.get("quarantine_reason"),
                    pid,
                ),
            )
            ev.commit()
            outcome["eligibility_class"] = eligibility
            outcome["prediction_scope"] = frozen.get("prediction_scope")
            outcome["public_visible"] = int(frozen.get("public_visible") or 0)

        outcome["fixture_id"] = fid
        outcome["freeze_id"] = pid
        outcome["result_sync"] = sync
        outcome["integrity"] = integrity
        return outcome
    finally:
        if own_prod:
            prod.close()
        if own_eval:
            ev.close()


def sync_and_evaluate_fixture(
    fixture_id: int,
    *,
    freeze_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Convenience: sync result then evaluate one frozen prediction."""
    return evaluate_frozen_prediction(
        fixture_id,
        freeze_id=freeze_id,
        dry_run=dry_run,
    )
