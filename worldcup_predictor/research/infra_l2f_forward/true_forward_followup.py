"""True-forward result follow-up (DB-first, provider fallback, evaluation after FT)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture
from worldcup_predictor.research.infra_l2f_forward.forward_hook import RUN_ID
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    evaluate_shadow_against_result,
    free_gb_from_df_line,
)
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.result_recovery import df_line

PENDING_NOT_STARTED = "pending_not_started"
PENDING_IN_PROGRESS = "pending_in_progress"
PENDING_GRACE = "pending_grace_period"
RECOVERED_DB = "result_recovered_db"
RECOVERED_PROVIDER = "result_recovered_provider"
POSTPONED = "postponed"
CANCELLED = "cancelled"
ABANDONED = "abandoned"
CONFLICT = "conflicting_result"
UNRESOLVED_PROVIDER = "unresolved_provider"


@dataclass
class FollowupBatchResult:
    dry_run: bool
    processed: int = 0
    by_class: dict[str, int] = field(default_factory=dict)
    evaluated: int = 0
    fixture_ids: list[int] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str | None = None
    disk_before: str | None = None
    disk_after: str | None = None


def _parse(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace(" ", "T")
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def _bump(out: FollowupBatchResult, cls: str) -> None:
    out.by_class[cls] = out.by_class.get(cls, 0) + 1


def list_true_forward_pending(
    fi_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    ensure_job_schema(fi_conn)
    rows = fi_conn.execute(
        f"""
        SELECT fixture_id, freeze_id, kickoff_utc, created_at_utc, status
        FROM {JOB_TABLE}
        WHERE run_id=? AND status='success'
        ORDER BY fixture_id ASC
        """,
        (RUN_ID,),
    ).fetchall()
    out = []
    for r in rows:
        fid = int(r[0])
        has = eval_conn.execute(
            "SELECT 1 FROM actual_results WHERE fixture_id=? AND actual_home_goals IS NOT NULL",
            (fid,),
        ).fetchone()
        if has:
            continue
        out.append(
            {
                "fixture_id": fid,
                "freeze_id": r[1],
                "kickoff_utc": r[2],
                "created_at_utc": r[3],
            }
        )
    return out


def classify_pre_sync(
    *,
    kickoff_utc: str | None,
    fixture_status: str | None,
    now: datetime | None = None,
    grace_hours: float = 2.5,
) -> str | None:
    """Return a pending class if too early to sync; else None to proceed."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    ko = _parse(kickoff_utc)
    st = str(fixture_status or "NS").upper()
    if st in {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "INPLAY"}:
        return PENDING_IN_PROGRESS
    if ko is None:
        return None
    if now < ko:
        return PENDING_NOT_STARTED
    # Expected FT ~105 minutes after kickoff + grace
    expected_ft = ko + timedelta(minutes=105)
    grace_end = expected_ft + timedelta(hours=float(grace_hours))
    if now < grace_end and st in {"NS", "TBD", "SUSP"}:
        if now < expected_ft:
            return PENDING_IN_PROGRESS
        return PENDING_GRACE
    return None


def map_sync_to_followup_class(sync_out: dict[str, Any], *, had_prod_result: bool) -> str:
    reason = str(sync_out.get("reason") or "").lower()
    quality = str(sync_out.get("result_quality_status") or "").upper()
    status = str(sync_out.get("status") or "").lower()
    if sync_out.get("conflict") or "conflict" in reason:
        return CONFLICT
    if quality == "POSTPONED" or "postponed" in reason:
        return POSTPONED
    if quality == "CANCELLED" or "cancelled" in reason:
        return CANCELLED
    if quality == "ABANDONED" or "abandoned" in reason:
        return ABANDONED
    if sync_out.get("result_available") and (
        sync_out.get("synced") or sync_out.get("inserted") or sync_out.get("reused") or status in {"ok", "synced", "reused"}
    ):
        return RECOVERED_DB if had_prod_result or sync_out.get("reused") else RECOVERED_PROVIDER
    if "api_football" in reason or "no_provider" in reason or "provider" in reason:
        return UNRESOLVED_PROVIDER
    if "not_terminal" in reason or "not_finished" in reason:
        return PENDING_IN_PROGRESS
    return UNRESOLVED_PROVIDER


def run_true_forward_followup_batch(
    *,
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection,
    fi_conn: sqlite3.Connection,
    batch_size: int = 20,
    dry_run: bool = True,
    grace_hours: float = 2.5,
    allow_provider: bool = True,
    min_free_gb: float = 8.0,
    settings: Any | None = None,
) -> FollowupBatchResult:
    disk = df_line()
    out = FollowupBatchResult(dry_run=dry_run, disk_before=disk)
    free = free_gb_from_df_line(disk)
    if free is not None and free < min_free_gb:
        out.stopped_reason = f"disk_free_below_{min_free_gb}G"
        return out

    pending = list_true_forward_pending(fi_conn, eval_conn)[: max(0, int(batch_size))]
    for item in pending:
        fid = int(item["fixture_id"])
        out.processed += 1
        out.fixture_ids.append(fid)
        detail: dict[str, Any] = {"fixture_id": fid, "freeze_id": item.get("freeze_id")}

        fx_status = None
        try:
            row = prod_conn.execute("SELECT status FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
            fx_status = row[0] if row else None
        except Exception:
            fx_status = None

        early = classify_pre_sync(
            kickoff_utc=item.get("kickoff_utc"),
            fixture_status=fx_status,
            grace_hours=grace_hours,
        )
        if early:
            detail["classification"] = early
            _bump(out, early)
            out.details.append(detail)
            continue

        had_prod = False
        try:
            pr = prod_conn.execute(
                "SELECT home_goals, away_goals FROM fixture_results WHERE fixture_id=?",
                (fid,),
            ).fetchone()
            had_prod = bool(pr and pr[0] is not None and pr[1] is not None)
        except Exception:
            had_prod = False

        if dry_run:
            detail["classification"] = "dry_run_eligible"
            detail["had_prod_result"] = had_prod
            _bump(out, "dry_run_eligible")
            out.details.append(detail)
            continue

        sync_out = sync_result_for_fixture(
            fid,
            prod_conn=prod_conn,
            eval_conn=eval_conn,
            settings=settings,
            dry_run=False,
            allow_provider_fetch=allow_provider,
        )
        cls = map_sync_to_followup_class(sync_out, had_prod_result=had_prod)
        detail["classification"] = cls
        detail["sync"] = {
            "status": sync_out.get("status"),
            "reason": sync_out.get("reason"),
            "regulation_score": sync_out.get("regulation_score"),
            "result_content_hash": sync_out.get("result_content_hash"),
            "provider": sync_out.get("provider"),
        }
        _bump(out, cls)

        if cls in (RECOVERED_DB, RECOVERED_PROVIDER):
            ar = eval_conn.execute(
                "SELECT actual_home_goals, actual_away_goals FROM actual_results WHERE fixture_id=?",
                (fid,),
            ).fetchone()
            if ar and ar[0] is not None and ar[1] is not None:
                n = evaluate_shadow_against_result(
                    fi_conn,
                    fixture_id=fid,
                    freeze_id=item.get("freeze_id"),
                    run_id=RUN_ID,
                    cohort_type="true_forward",
                    actual_home=int(ar[0]),
                    actual_away=int(ar[1]),
                    canonical_top5=None,
                )
                detail["eval_rows"] = n
                if n > 0:
                    out.evaluated += 1

        out.details.append(detail)

    out.disk_after = df_line()
    return out
