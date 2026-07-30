"""Phase 3 — safe result recovery for freezes missing actual_results (eval DB)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture
from worldcup_predictor.research.infra_l2f_forward.historical_cohort import OWNER_SCOPES, _parse_dt
from worldcup_predictor.research.infra_l2f_forward.historical_replay import (
    COHORT_HISTORICAL,
    EVAL_TABLE,
    ensure_replay_schema,
    evaluate_shadow_against_result,
    free_gb_from_df_line,
)
from worldcup_predictor.research.infra_l2f_forward.job_store import JOB_TABLE, ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow
from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE

logger = logging.getLogger(__name__)

CLASS_RECOVERED_DB = "result_recovered_db"
CLASS_RECOVERED_PROVIDER = "result_recovered_provider"
CLASS_ALREADY_PRESENT = "result_already_present"
CLASS_NOT_FINISHED = "fixture_not_finished"
CLASS_POSTPONED = "postponed_or_cancelled"
CLASS_PROVIDER_UNAVAILABLE = "provider_unavailable"
CLASS_AMBIGUOUS = "ambiguous_fixture_identity"
CLASS_CONFLICT = "conflicting_result"
CLASS_UNRESOLVED = "permanently_unresolved"

COHORT_RECOVERED = "historical_replay_result_recovered"
CHECKPOINT_TABLE = "l2f_result_recovery_checkpoints"

CHECKPOINT_DDL = f"""
CREATE TABLE IF NOT EXISTS {CHECKPOINT_TABLE} (
    checkpoint_id TEXT PRIMARY KEY,
    run_label TEXT NOT NULL,
    last_fixture_id INTEGER,
    processed INTEGER NOT NULL DEFAULT 0,
    recovered INTEGER NOT NULL DEFAULT 0,
    evaluated INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    updated_at_utc TEXT NOT NULL
)
"""


@dataclass
class MissingResultFreeze:
    freeze_id: str
    fixture_id: int
    kickoff: str | None
    frozen_at: str | None
    prediction_scope: str | None
    competition: str | None
    lambda_home: float | None
    lambda_away: float | None
    classification: str | None = None
    block_reason: str | None = None
    actual_home: int | None = None
    actual_away: int | None = None
    result_source: str | None = None
    result_content_hash: str | None = None


@dataclass
class RecoveryBatchResult:
    dry_run: bool
    processed: int = 0
    recovered_db: int = 0
    recovered_provider: int = 0
    already_present: int = 0
    not_finished: int = 0
    postponed_or_cancelled: int = 0
    provider_unavailable: int = 0
    ambiguous: int = 0
    conflicting: int = 0
    unresolved: int = 0
    evaluated: int = 0
    shadow_generated: int = 0
    fixture_ids: list[int] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    stopped_reason: str | None = None
    disk_before: str | None = None
    disk_after: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def df_line() -> str:
    try:
        out = subprocess.check_output(["df", "-h", "/"], text=True)
        return out.strip().splitlines()[-1]
    except Exception:
        return "N/A"


def ensure_recovery_schema(fi_conn: sqlite3.Connection) -> None:
    ensure_replay_schema(fi_conn)
    ensure_job_schema(fi_conn)
    fi_conn.execute(CHECKPOINT_DDL)
    fi_conn.commit()


def inventory_missing_result_freezes(
    eval_conn: sqlite3.Connection,
    *,
    scopes: Iterable[str] | None = None,
) -> list[MissingResultFreeze]:
    """First ACTIVE freeze per fixture that lacks evaluable actual_results."""
    eval_conn.row_factory = sqlite3.Row
    scopes = list(scopes or OWNER_SCOPES)
    placeholders = ",".join("?" for _ in scopes)
    rows = eval_conn.execute(
        f"""
        SELECT
          f.prediction_id AS freeze_id,
          f.fixture_id,
          f.kickoff,
          f.frozen_at,
          f.prediction_scope,
          f.competition,
          f.lambda_home,
          f.lambda_away,
          f.freeze_status,
          f.quarantine_reason,
          a.actual_score,
          a.actual_home_goals
        FROM frozen_predictions f
        LEFT JOIN actual_results a ON a.fixture_id = f.fixture_id
        WHERE IFNULL(f.prediction_scope, '') IN ({placeholders})
        ORDER BY f.fixture_id ASC, f.frozen_at ASC
        """,
        scopes,
    ).fetchall()
    out: list[MissingResultFreeze] = []
    seen: set[int] = set()
    for r in rows:
        fid = int(r["fixture_id"])
        if fid in seen:
            continue
        seen.add(fid)
        has_result = r["actual_score"] is not None and r["actual_home_goals"] is not None
        if has_result:
            continue
        if r["freeze_status"] and str(r["freeze_status"]).upper() not in ("ACTIVE", ""):
            continue
        if r["quarantine_reason"]:
            continue
        if r["lambda_home"] is None or r["lambda_away"] is None:
            continue
        fr = _parse_dt(r["frozen_at"])
        ko = _parse_dt(r["kickoff"])
        if fr is None or ko is None or fr >= ko:
            continue
        out.append(
            MissingResultFreeze(
                freeze_id=str(r["freeze_id"]),
                fixture_id=fid,
                kickoff=r["kickoff"],
                frozen_at=r["frozen_at"],
                prediction_scope=r["prediction_scope"],
                competition=r["competition"],
                lambda_home=float(r["lambda_home"]),
                lambda_away=float(r["lambda_away"]),
            )
        )
    return out


def classify_sync_outcome(sync_out: dict[str, Any], *, used_provider: bool) -> str:
    reason = str(sync_out.get("reason") or "").lower()
    status = str(sync_out.get("status") or "").lower()
    quality = str(sync_out.get("result_quality_status") or "").upper()

    if sync_out.get("reused") or reason in {"eval_actual_result_exists", "already_synced"}:
        return CLASS_ALREADY_PRESENT
    if sync_out.get("conflict") or quality == "PROVIDER_CONFLICT" or "conflict" in reason:
        return CLASS_CONFLICT
    if quality in {"POSTPONED", "CANCELLED", "ABANDONED"} or any(
        x in reason for x in ("postponed", "cancelled", "abandoned")
    ):
        return CLASS_POSTPONED
    if any(
        x in reason
        for x in (
            "not_terminal",
            "provider_not_finished",
            "status_not_terminal",
            "result_not_available",
        )
    ) or status in {"blocked"} and not sync_out.get("result_available"):
        if quality in {"POSTPONED", "CANCELLED", "ABANDONED"}:
            return CLASS_POSTPONED
        # Distinguish unfinished vs unavailable
        if "api_football" in reason or "no_provider" in reason or "not_configured" in reason:
            return CLASS_PROVIDER_UNAVAILABLE
        if "fixture_not_found" in reason or "ambiguous" in reason:
            return CLASS_AMBIGUOUS
        if sync_out.get("result_available") is False and (
            "not_finished" in reason or "not_terminal" in reason or "provider_not_finished" in reason
        ):
            return CLASS_NOT_FINISHED
        if sync_out.get("result_available"):
            return CLASS_UNRESOLVED
        return CLASS_NOT_FINISHED
    if "fixture_not_found" in reason or "ambiguous" in reason or "parse_failed" in reason:
        return CLASS_AMBIGUOUS
    if "api_football_not_configured" in reason or "no_provider_data" in reason or "provider_unavailable" in reason:
        return CLASS_PROVIDER_UNAVAILABLE
    if sync_out.get("result_available") and (
        sync_out.get("synced") or sync_out.get("inserted") or status in {"ok", "synced", "dry_run", "success"}
    ):
        return CLASS_RECOVERED_PROVIDER if used_provider else CLASS_RECOVERED_DB
    if sync_out.get("result_available") and status == "dry_run":
        return CLASS_RECOVERED_PROVIDER if used_provider else CLASS_RECOVERED_DB
    if sync_out.get("synced"):
        return CLASS_RECOVERED_PROVIDER if used_provider else CLASS_RECOVERED_DB
    return CLASS_UNRESOLVED


def _canonical_top5(eval_conn: sqlite3.Connection, freeze_id: str) -> int | None:
    try:
        row = eval_conn.execute(
            "SELECT ecse_top5_hit FROM market_evaluations WHERE prediction_id=?",
            (freeze_id,),
        ).fetchone()
        if not row:
            return None
        v = row[0] if not isinstance(row, sqlite3.Row) else row["ecse_top5_hit"]
        if v in (1, True, "HIT", "hit", "1"):
            return 1
        if v in (0, False, "MISS", "miss", "0"):
            return 0
        return None
    except Exception:
        return None


def _has_shadow(fi_conn: sqlite3.Connection, fixture_id: int) -> bool:
    try:
        n = fi_conn.execute(
            f"SELECT COUNT(*) FROM {SHADOW_TABLE} WHERE fixture_id=?",
            (int(fixture_id),),
        ).fetchone()[0]
        return int(n) > 0
    except Exception:
        return False


def _load_actual(eval_conn: sqlite3.Connection, fixture_id: int) -> tuple[int, int, str | None, str | None] | None:
    row = eval_conn.execute(
        """
        SELECT actual_home_goals, actual_away_goals, result_source, result_content_hash
        FROM actual_results WHERE fixture_id=?
        """,
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    if row[0] is None or row[1] is None:
        return None
    return int(row[0]), int(row[1]), row[2], row[3]


def run_result_recovery_batch(
    *,
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection,
    fi_conn: sqlite3.Connection,
    batch_size: int = 20,
    dry_run: bool = True,
    allow_provider: bool = True,
    min_free_gb: float = 8.0,
    disk_line: str | None = None,
    resume_after_fixture_id: int | None = None,
    generate_missing_shadow: bool = True,
    run_label: str = "l2f-result-recovery",
    settings: Any | None = None,
) -> RecoveryBatchResult:
    """Bounded recovery + optional shadow backfill + evaluation. Never mutates freezes."""
    out = RecoveryBatchResult(dry_run=dry_run, disk_before=disk_line)
    free = free_gb_from_df_line(disk_line) if disk_line else None
    if free is not None and free < min_free_gb:
        out.stopped_reason = f"disk_free_below_{min_free_gb}G"
        return out

    ensure_recovery_schema(fi_conn)
    missing = inventory_missing_result_freezes(eval_conn)
    if resume_after_fixture_id is not None:
        missing = [m for m in missing if m.fixture_id > int(resume_after_fixture_id)]
    batch = missing[: max(0, int(batch_size))]

    for m in batch:
        out.processed += 1
        out.fixture_ids.append(m.fixture_id)
        detail: dict[str, Any] = {
            "fixture_id": m.fixture_id,
            "freeze_id": m.freeze_id,
            "competition": m.competition,
            "kickoff": m.kickoff,
        }

        # Detect whether prod DB already has a terminal result (for classification source).
        had_prod_result = False
        try:
            pr = prod_conn.execute(
                "SELECT home_goals, away_goals, final_stage FROM fixture_results WHERE fixture_id=?",
                (m.fixture_id,),
            ).fetchone()
            had_prod_result = bool(pr and pr[0] is not None and pr[1] is not None)
        except Exception:
            had_prod_result = False

        sync_out = sync_result_for_fixture(
            m.fixture_id,
            prod_conn=prod_conn,
            eval_conn=eval_conn,
            settings=settings,
            dry_run=dry_run,
            allow_provider_fetch=allow_provider,
        )
        used_provider = (not had_prod_result) and allow_provider and not sync_out.get("reused")
        # If dry-run provider path indicated fetch, mark provider
        if dry_run and not had_prod_result and sync_out.get("result_available"):
            used_provider = True
        if had_prod_result and sync_out.get("result_available"):
            used_provider = False

        cls = classify_sync_outcome(sync_out, used_provider=used_provider)
        detail["classification"] = cls
        detail["sync"] = {
            "status": sync_out.get("status"),
            "reason": sync_out.get("reason"),
            "result_available": sync_out.get("result_available"),
            "regulation_score": sync_out.get("regulation_score"),
            "result_content_hash": sync_out.get("result_content_hash"),
            "provider": sync_out.get("provider"),
        }
        m.classification = cls

        _bump_class(out, cls)

        if dry_run:
            out.details.append(detail)
            continue

        actual = _load_actual(eval_conn, m.fixture_id)
        if actual is None:
            out.details.append(detail)
            _save_checkpoint(fi_conn, run_label, m.fixture_id, out)
            continue

        ah, aa, src, rhash = actual
        detail["actual_home"] = ah
        detail["actual_away"] = aa
        detail["result_source"] = src
        detail["result_content_hash"] = rhash

        # Kickoff consistency soft-check
        ko = _parse_dt(m.kickoff)
        if ko is not None and datetime.now(timezone.utc).replace(tzinfo=None) < ko:
            detail["warning"] = "result_before_expected_kickoff_window"
            # still allow if DB says finished — mark conflict-ish only if clearly future
            if cls in (CLASS_RECOVERED_DB, CLASS_RECOVERED_PROVIDER, CLASS_ALREADY_PRESENT):
                detail["classification"] = CLASS_CONFLICT
                out.conflicting += 1
                _unbump_class(out, cls)
                out.details.append(detail)
                _save_checkpoint(fi_conn, run_label, m.fixture_id, out)
                continue

        if generate_missing_shadow and not _has_shadow(fi_conn, m.fixture_id):
            freeze_meta = {
                "capture_status": "reused",
                "freeze_id": m.freeze_id,
                "prediction_scope": m.prediction_scope or "owner_shadow",
                "quarantined": False,
                "conflict_detected": False,
                "cohort_type": COHORT_RECOVERED,
                "frozen_at": m.frozen_at,
                "kickoff": m.kickoff,
                "canonical_lambda_home": m.lambda_home,
                "canonical_lambda_away": m.lambda_away,
            }
            meta = maybe_run_l2f_forward_shadow(
                conn=fi_conn,
                fixture_id=m.fixture_id,
                freeze_meta=freeze_meta,
                prediction_scope=m.prediction_scope or "owner_shadow",
                settings=settings,
                backfill=True,
            )
            detail["shadow"] = {
                "status": meta.get("status"),
                "reason": meta.get("reason"),
                "lambda_rows": meta.get("lambda_rows"),
                "exact_rows": meta.get("exact_rows"),
            }
            if meta.get("status") == "success":
                out.shadow_generated += 1

        if _has_shadow(fi_conn, m.fixture_id):
            n = evaluate_shadow_against_result(
                fi_conn,
                fixture_id=m.fixture_id,
                freeze_id=m.freeze_id,
                run_id="l2f-forward-v1-result-recovery",
                cohort_type=COHORT_RECOVERED,
                actual_home=ah,
                actual_away=aa,
                canonical_top5=_canonical_top5(eval_conn, m.freeze_id),
            )
            detail["eval_rows"] = n
            if n > 0:
                out.evaluated += 1

        out.details.append(detail)
        _save_checkpoint(fi_conn, run_label, m.fixture_id, out)

    return out


def _bump_class(out: RecoveryBatchResult, cls: str) -> None:
    if cls == CLASS_RECOVERED_DB:
        out.recovered_db += 1
    elif cls == CLASS_RECOVERED_PROVIDER:
        out.recovered_provider += 1
    elif cls == CLASS_ALREADY_PRESENT:
        out.already_present += 1
    elif cls == CLASS_NOT_FINISHED:
        out.not_finished += 1
    elif cls == CLASS_POSTPONED:
        out.postponed_or_cancelled += 1
    elif cls == CLASS_PROVIDER_UNAVAILABLE:
        out.provider_unavailable += 1
    elif cls == CLASS_AMBIGUOUS:
        out.ambiguous += 1
    elif cls == CLASS_CONFLICT:
        out.conflicting += 1
    else:
        out.unresolved += 1


def _unbump_class(out: RecoveryBatchResult, cls: str) -> None:
    if cls == CLASS_RECOVERED_DB and out.recovered_db:
        out.recovered_db -= 1
    elif cls == CLASS_RECOVERED_PROVIDER and out.recovered_provider:
        out.recovered_provider -= 1
    elif cls == CLASS_ALREADY_PRESENT and out.already_present:
        out.already_present -= 1
    elif cls == CLASS_NOT_FINISHED and out.not_finished:
        out.not_finished -= 1
    elif cls == CLASS_POSTPONED and out.postponed_or_cancelled:
        out.postponed_or_cancelled -= 1
    elif cls == CLASS_PROVIDER_UNAVAILABLE and out.provider_unavailable:
        out.provider_unavailable -= 1
    elif cls == CLASS_AMBIGUOUS and out.ambiguous:
        out.ambiguous -= 1
    elif cls == CLASS_UNRESOLVED and out.unresolved:
        out.unresolved -= 1


def _save_checkpoint(fi_conn: sqlite3.Connection, run_label: str, last_fx: int, out: RecoveryBatchResult) -> None:
    ensure_recovery_schema(fi_conn)
    cid = f"ckpt-{run_label}"
    fi_conn.execute(
        f"""
        INSERT INTO {CHECKPOINT_TABLE} (
            checkpoint_id, run_label, last_fixture_id, processed, recovered, evaluated, blocked, failed, updated_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(checkpoint_id) DO UPDATE SET
            last_fixture_id=excluded.last_fixture_id,
            processed=excluded.processed,
            recovered=excluded.recovered,
            evaluated=excluded.evaluated,
            blocked=excluded.blocked,
            failed=excluded.failed,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            cid,
            run_label,
            int(last_fx),
            out.processed,
            out.recovered_db + out.recovered_provider,
            out.evaluated,
            out.not_finished + out.postponed_or_cancelled + out.ambiguous + out.conflicting,
            out.unresolved + out.provider_unavailable,
            _now(),
        ),
    )
    fi_conn.commit()


def summarize_inventory(items: list[MissingResultFreeze]) -> dict[str, Any]:
    by_comp: dict[str, int] = {}
    by_date: dict[str, int] = {}
    for m in items:
        by_comp[m.competition or "unknown"] = by_comp.get(m.competition or "unknown", 0) + 1
        d = (m.kickoff or "")[:10]
        by_date[d] = by_date.get(d, 0) + 1
    return {
        "total_missing_result_freezes": len(items),
        "by_competition": dict(sorted(by_comp.items(), key=lambda x: -x[1])),
        "by_kickoff_date": dict(sorted(by_date.items(), key=lambda x: -x[1])[:30]),
        "fixture_ids": [m.fixture_id for m in items],
    }


def write_inventory(items: list[MissingResultFreeze], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(m) for m in items]
    path.write_text(json.dumps({"summary": summarize_inventory(items), "rows": rows}, indent=2), encoding="utf-8")
