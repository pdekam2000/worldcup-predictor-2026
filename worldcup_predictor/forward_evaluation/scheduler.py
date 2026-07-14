"""Phase 2E — Forward evaluation scheduler-safe batch orchestrator."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.constants import (
    EVAL_COMPLETE,
    NON_TERMINAL_STATUSES,
    TERMINAL_STATUSES,
)
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.evaluation_service import evaluate_frozen_prediction
from worldcup_predictor.forward_evaluation.freeze_integrity import verify_freeze_integrity
from worldcup_predictor.forward_evaluation.lock import SchedulerLockActive, scheduler_cycle_lock
from worldcup_predictor.forward_evaluation.result_record import (
    ELIGIBILITY_OWNER_ONLY,
    ELIGIBILITY_PUBLIC,
    ELIGIBILITY_QUARANTINED,
)
from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture
from worldcup_predictor.forward_evaluation.results import is_evaluable_status

# Classification labels
RESULT_SYNC_REQUIRED = "RESULT_SYNC_REQUIRED"
RESULT_ALREADY_CONFIRMED = "RESULT_ALREADY_CONFIRMED"
RESULT_NOT_AVAILABLE = "RESULT_NOT_AVAILABLE"
RESULT_CONFLICT = "RESULT_CONFLICT"
FREEZE_PENDING_EVALUATION = "FREEZE_PENDING_EVALUATION"
ALREADY_EVALUATED = "ALREADY_EVALUATED"
FREEZE_INVALID = "FREEZE_INVALID"
OWNER_ONLY = "OWNER_ONLY"
PUBLIC_ELIGIBLE = "PUBLIC_ELIGIBLE"
QUARANTINED = "QUARANTINED"
OUTSIDE_LOOKBACK = "OUTSIDE_LOOKBACK"
LIMIT_DEFERRED = "LIMIT_DEFERRED"

# Dry-run action labels
WOULD_INSERT_RESULT = "WOULD_INSERT_RESULT"
WOULD_REUSE_RESULT = "WOULD_REUSE_RESULT"
WOULD_INSERT_EVALUATION = "WOULD_INSERT_EVALUATION"
WOULD_REUSE_EVALUATION = "WOULD_REUSE_EVALUATION"
WOULD_BLOCK_FREEZE = "WOULD_BLOCK_FREEZE"
WOULD_BLOCK_RESULT = "WOULD_BLOCK_RESULT"
WOULD_QUARANTINE = "WOULD_QUARANTINE"
WOULD_DEFER_LIMIT = "WOULD_DEFER_LIMIT"

DEFAULT_FIXTURE_LIMIT = 25
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_PROVIDER_CALL_LIMIT = 25
DEFAULT_MAX_RUNTIME_SECONDS = 900
DEFAULT_MAX_RESULT_INSERTS = 25
DEFAULT_MAX_EVAL_INSERTS = 25
DEFAULT_MAX_PROVIDER_ERRORS = 5

FINAL_OK = "FORWARD_EVALUATION_CYCLE_COMPLETE"
FINAL_ALREADY_RUNNING = "FORWARD_EVALUATION_CYCLE_ALREADY_RUNNING"
FINAL_LIMIT_REACHED = "FORWARD_EVALUATION_CYCLE_LIMIT_REACHED"
FINAL_RUNTIME_EXCEEDED = "FORWARD_EVALUATION_CYCLE_RUNTIME_EXCEEDED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00").replace(" UTC", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root()),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def _scope_matches(scope_filter: str | None, prediction_scope: str | None) -> bool:
    if not scope_filter or scope_filter == "all":
        return True
    actual = str(prediction_scope or "production")
    return actual == scope_filter


def _eligibility_bucket(frozen: dict[str, Any]) -> str:
    scope = str(frozen.get("prediction_scope") or "production")
    tier = str(frozen.get("validation_tier") or "A")
    if frozen.get("quarantine_reason"):
        return QUARANTINED
    if scope in ("owner_shadow", "owner_daily") or tier == "B" or int(frozen.get("public_visible") or 0) == 0:
        return OWNER_ONLY
    return PUBLIC_ELIGIBLE


def _load_pending_freezes(eval_conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = eval_conn.execute(
        """
        SELECT * FROM frozen_predictions
        WHERE freeze_status='ACTIVE'
        ORDER BY kickoff DESC, frozen_at DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _fixture_status(prod_conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    try:
        row = prod_conn.execute(
            """
            SELECT f.fixture_id, f.status, f.kickoff_utc,
                   fr.regulation_home_goals, fr.regulation_away_goals, fr.final_stage
            FROM fixtures f
            LEFT JOIN fixture_results fr ON f.fixture_id = fr.fixture_id
            WHERE f.fixture_id=? AND (f.is_placeholder IS NULL OR f.is_placeholder=0)
            LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
    except sqlite3.OperationalError:
        row = prod_conn.execute(
            """
            SELECT fixture_id, status, kickoff_utc
            FROM fixtures
            WHERE fixture_id=? AND (is_placeholder IS NULL OR is_placeholder=0)
            LIMIT 1
            """,
            (int(fixture_id),),
        ).fetchone()
    return dict(row) if row else None


def _has_eval_row(eval_conn: sqlite3.Connection, prediction_id: str) -> bool:
    return (
        eval_conn.execute(
            "SELECT 1 FROM market_evaluations WHERE prediction_id=?",
            (prediction_id,),
        ).fetchone()
        is not None
    )


def _has_actual_result(eval_conn: sqlite3.Connection, fixture_id: int) -> bool:
    return (
        eval_conn.execute(
            "SELECT 1 FROM actual_results WHERE fixture_id=?",
            (int(fixture_id),),
        ).fetchone()
        is not None
    )


def _classify_candidate(
    *,
    frozen: dict[str, Any],
    fixture: dict[str, Any] | None,
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection,
    lookback_cutoff: datetime,
    now: datetime,
) -> tuple[str, dict[str, Any]]:
    fid = int(frozen["fixture_id"])
    pid = str(frozen["prediction_id"])
    kickoff = _parse_dt(frozen.get("kickoff") or (fixture or {}).get("kickoff_utc"))
    detail: dict[str, Any] = {
        "fixture_id": fid,
        "freeze_id": pid,
        "prediction_scope": frozen.get("prediction_scope"),
        "validation_tier": frozen.get("validation_tier"),
    }

    if kickoff and kickoff < lookback_cutoff:
        detail["kickoff"] = kickoff.isoformat()
        return OUTSIDE_LOOKBACK, detail
    if kickoff and kickoff > now:
        detail["kickoff"] = kickoff.isoformat()
        return FREEZE_INVALID, detail

    if frozen.get("quarantine_reason"):
        return QUARANTINED, detail

    integrity = verify_freeze_integrity(eval_conn, prod_conn, prediction_id=pid)
    if not integrity.get("ok"):
        detail["integrity_reason"] = integrity.get("reason_code")
        return FREEZE_INVALID, detail

    status = str((fixture or {}).get("status") or "NS").upper()
    if status in {"PST", "POSTPONED", "CANC", "CANCELLED", "ABD", "ABANDONED"}:
        detail["fixture_status"] = status
        return RESULT_NOT_AVAILABLE, detail

    if _has_eval_row(eval_conn, pid):
        detail["evaluation_status"] = EVAL_COMPLETE
        return ALREADY_EVALUATED, detail

    bucket = _eligibility_bucket(frozen)
    detail["eligibility_bucket"] = bucket

    if not is_evaluable_status(status) and not _has_actual_result(eval_conn, fid):
        if status in NON_TERMINAL_STATUSES or status not in TERMINAL_STATUSES:
            detail["fixture_status"] = status
            return RESULT_NOT_AVAILABLE, detail

    if _has_actual_result(eval_conn, fid):
        detail["result_state"] = "confirmed"
        return FREEZE_PENDING_EVALUATION if bucket != QUARANTINED else QUARANTINED, detail

    detail["fixture_status"] = status
    return RESULT_SYNC_REQUIRED, detail


def _plan_result_action(sync_out: dict[str, Any]) -> str:
    if sync_out.get("conflict"):
        return WOULD_BLOCK_RESULT
    if sync_out.get("reused"):
        return WOULD_REUSE_RESULT
    if sync_out.get("inserted"):
        return WOULD_INSERT_RESULT
    if sync_out.get("result_available"):
        return WOULD_REUSE_RESULT
    return WOULD_BLOCK_RESULT


def _plan_eval_action(eval_out: dict[str, Any]) -> str:
    if eval_out.get("reason") == "already_evaluated":
        return WOULD_REUSE_EVALUATION
    if eval_out.get("would_evaluate"):
        return WOULD_INSERT_EVALUATION
    if eval_out.get("evaluated"):
        return WOULD_INSERT_EVALUATION
    reason = eval_out.get("reason")
    if reason in {"FREEZE_MISSING", "POST_KICKOFF_FREEZE", "POST_KICKOFF_PREDICTION", "CONTENT_HASH_MISMATCH"}:
        return WOULD_BLOCK_FREEZE
    if eval_out.get("eligibility_class") == ELIGIBILITY_QUARANTINED:
        return WOULD_QUARANTINE
    return WOULD_BLOCK_RESULT


def _insert_run_ledger(eval_conn: sqlite3.Connection, ledger: dict[str, Any]) -> None:
    eval_conn.execute(
        """
        INSERT INTO forward_evaluation_runs (
            run_id, started_at_utc, completed_at_utc, dry_run, source_commit,
            fixture_limit, lookback_hours, scope_filter, candidates_found,
            results_inserted, results_reused, results_missing, result_conflicts,
            freezes_valid, freezes_invalid, evaluations_inserted, evaluations_reused,
            unavailable_components, public_eligible_count, owner_only_count,
            quarantined_count, provider_calls, provider_errors, final_status, ledger_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ledger["run_id"],
            ledger["started_at_utc"],
            ledger.get("completed_at_utc"),
            1 if ledger.get("dry_run") else 0,
            ledger.get("source_commit"),
            ledger.get("fixture_limit"),
            ledger.get("lookback_hours"),
            ledger.get("scope_filter"),
            ledger.get("candidates_found", 0),
            ledger.get("results_inserted", 0),
            ledger.get("results_reused", 0),
            ledger.get("results_missing", 0),
            ledger.get("result_conflicts", 0),
            ledger.get("freezes_valid", 0),
            ledger.get("freezes_invalid", 0),
            ledger.get("evaluations_inserted", 0),
            ledger.get("evaluations_reused", 0),
            ledger.get("unavailable_components", 0),
            ledger.get("public_eligible_count", 0),
            ledger.get("owner_only_count", 0),
            ledger.get("quarantined_count", 0),
            ledger.get("provider_calls", 0),
            ledger.get("provider_errors", 0),
            ledger.get("final_status"),
            json.dumps(ledger, default=str),
        ),
    )
    eval_conn.commit()


def run_forward_evaluation_cycle(
    *,
    dry_run: bool = True,
    fixture_limit: int = DEFAULT_FIXTURE_LIMIT,
    scope: str | None = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    fixture_ids: list[int] | None = None,
    provider_call_limit: int = DEFAULT_PROVIDER_CALL_LIMIT,
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS,
    max_result_inserts: int = DEFAULT_MAX_RESULT_INSERTS,
    max_eval_inserts: int = DEFAULT_MAX_EVAL_INSERTS,
    max_provider_errors: int = DEFAULT_MAX_PROVIDER_ERRORS,
    skip_lock: bool = False,
    settings: Settings | None = None,
    prod_conn: sqlite3.Connection | None = None,
    eval_conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Canonical scheduler-safe forward evaluation cycle (result sync + market evaluation)."""
    settings = settings or get_settings()
    run_id = str(uuid.uuid4())
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    lookback_cutoff = now - timedelta(hours=int(lookback_hours))

    ledger: dict[str, Any] = {
        "run_id": run_id,
        "started_at_utc": _utc_now(),
        "dry_run": dry_run,
        "source_commit": _resolve_git_sha(),
        "fixture_limit": int(fixture_limit),
        "lookback_hours": int(lookback_hours),
        "scope_filter": scope or "all",
        "candidates_found": 0,
        "results_inserted": 0,
        "results_reused": 0,
        "results_missing": 0,
        "result_conflicts": 0,
        "freezes_valid": 0,
        "freezes_invalid": 0,
        "evaluations_inserted": 0,
        "evaluations_reused": 0,
        "unavailable_components": 0,
        "public_eligible_count": 0,
        "owner_only_count": 0,
        "quarantined_count": 0,
        "provider_calls": 0,
        "provider_errors": 0,
        "provider_call_limit": provider_call_limit,
        "max_runtime_seconds": max_runtime_seconds,
        "actions": [],
        "classifications": {},
        "deferred": [],
        "final_status": FINAL_OK,
    }

    def _inc_classification(label: str) -> None:
        ledger["classifications"][label] = ledger["classifications"].get(label, 0) + 1

    def _runtime_exceeded() -> bool:
        return (time.monotonic() - started) >= max_runtime_seconds

    def _execute_cycle() -> dict[str, Any]:
        own_prod = prod_conn is None
        own_eval = eval_conn is None
        prod = prod_conn or connect(settings.sqlite_path)
        ev = eval_conn or connect_eval_db(project_root())
        try:
            pending = _load_pending_freezes(ev)
            candidates: list[dict[str, Any]] = []
            for frozen in pending:
                if not _scope_matches(scope, frozen.get("prediction_scope")):
                    continue
                fid = int(frozen["fixture_id"])
                if fixture_ids and fid not in fixture_ids:
                    continue
                fixture = _fixture_status(prod, fid)
                label, detail = _classify_candidate(
                    frozen=frozen,
                    fixture=fixture,
                    eval_conn=ev,
                    prod_conn=prod,
                    lookback_cutoff=lookback_cutoff,
                    now=now,
                )
                _inc_classification(label)
                candidates.append({"frozen": frozen, "fixture": fixture, "classification": label, "detail": detail})

            ledger["candidates_found"] = len(candidates)

            processed_fixtures = 0
            seen_fixture_ids: set[int] = set()

            for item in candidates:
                if _runtime_exceeded():
                    ledger["final_status"] = FINAL_RUNTIME_EXCEEDED
                    break
                if processed_fixtures >= fixture_limit:
                    ledger["deferred"].append(
                        {"fixture_id": item["frozen"]["fixture_id"], "reason": LIMIT_DEFERRED}
                    )
                    _inc_classification(LIMIT_DEFERRED)
                    continue

                frozen = item["frozen"]
                fid = int(frozen["fixture_id"])
                pid = str(frozen["prediction_id"])
                classification = item["classification"]

                if classification in {OUTSIDE_LOOKBACK, FREEZE_INVALID, QUARANTINED, ALREADY_EVALUATED}:
                    if classification == FREEZE_INVALID:
                        ledger["freezes_invalid"] += 1
                    elif classification == QUARANTINED:
                        ledger["quarantined_count"] += 1
                    elif classification == ALREADY_EVALUATED:
                        ledger["evaluations_reused"] += 1
                    continue

                bucket = _eligibility_bucket(frozen)
                if bucket == PUBLIC_ELIGIBLE:
                    ledger["public_eligible_count"] += 1
                elif bucket == OWNER_ONLY:
                    ledger["owner_only_count"] += 1

                allow_provider = (
                    not dry_run
                    and ledger["provider_calls"] < provider_call_limit
                    and ledger["provider_errors"] < max_provider_errors
                )
                sync_out = sync_result_for_fixture(
                    fid,
                    prod_conn=prod,
                    eval_conn=ev,
                    settings=settings,
                    dry_run=dry_run,
                    allow_provider_fetch=allow_provider,
                )
                if sync_out.get("fetched") and not dry_run:
                    ledger["provider_calls"] += 1
                if sync_out.get("reason") in {"no_provider_data", "provider_not_finished", "api_football_not_configured"}:
                    if not dry_run:
                        ledger["provider_errors"] += 1

                result_action = _plan_result_action(sync_out)
                if sync_out.get("inserted"):
                    ledger["results_inserted"] += 1
                elif sync_out.get("reused"):
                    ledger["results_reused"] += 1
                elif sync_out.get("conflict"):
                    ledger["result_conflicts"] += 1
                    ledger["results_missing"] += 1
                elif not sync_out.get("result_available"):
                    ledger["results_missing"] += 1

                eval_out: dict[str, Any] = {"evaluated": False, "skipped": True}
                if sync_out.get("conflict"):
                    eval_action = WOULD_BLOCK_RESULT
                elif not sync_out.get("result_available") and not dry_run:
                    eval_action = WOULD_BLOCK_RESULT
                else:
                    ledger["freezes_valid"] += 1
                    eval_out = evaluate_frozen_prediction(
                        fid,
                        freeze_id=pid,
                        dry_run=dry_run,
                        prod_conn=prod,
                        eval_conn=ev,
                        skip_result_sync=True,
                    )
                    eval_action = _plan_eval_action(eval_out)
                    if eval_out.get("evaluated"):
                        if ledger["evaluations_inserted"] >= max_eval_inserts:
                            ledger["deferred"].append({"fixture_id": fid, "reason": LIMIT_DEFERRED})
                            _inc_classification(LIMIT_DEFERRED)
                            continue
                        ledger["evaluations_inserted"] += 1
                    elif eval_out.get("reason") == "already_evaluated":
                        ledger["evaluations_reused"] += 1

                ledger["actions"].append(
                    {
                        "fixture_id": fid,
                        "freeze_id": pid,
                        "classification": classification,
                        "result_action": result_action,
                        "eval_action": eval_action,
                        "eligibility_bucket": bucket,
                        "sync": sync_out,
                        "evaluation": eval_out,
                    }
                )

                if fid not in seen_fixture_ids:
                    seen_fixture_ids.add(fid)
                    processed_fixtures += 1

            if ledger["deferred"] and ledger["final_status"] == FINAL_OK:
                ledger["final_status"] = FINAL_LIMIT_REACHED

            ledger["completed_at_utc"] = _utc_now()
            ledger["runtime_seconds"] = round(time.monotonic() - started, 3)

            if not dry_run:
                _insert_run_ledger(ev, ledger)

            return ledger
        finally:
            if own_prod:
                prod.close()
            if own_eval:
                ev.close()

    if dry_run or skip_lock:
        return _execute_cycle()

    try:
        with scheduler_cycle_lock(
            run_id=run_id,
            dry_run=dry_run,
            fixture_limit=fixture_limit,
            lookback_hours=lookback_hours,
            scope=scope,
        ):
            return _execute_cycle()
    except SchedulerLockActive as exc:
        return {
            "run_id": run_id,
            "dry_run": dry_run,
            "final_status": FINAL_ALREADY_RUNNING,
            "reason": str(exc),
            "lock_detail": exc.detail,
        }
