"""Controlled historical replay / cohort bootstrap for L2-F shadow (non-canonical)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow
from worldcup_predictor.research.infra_l2f_forward.historical_cohort import (
    CLASS_ELIGIBLE_HISTORICAL,
    CLASS_ELIGIBLE_TRUE_FORWARD,
    FreezeCandidate,
    inventory_eval_db,
)
from worldcup_predictor.research.infra_l2f_forward.job_store import ensure_job_schema

logger = logging.getLogger(__name__)

COHORT_HISTORICAL = "historical_replay"
COHORT_TRUE_FORWARD = "true_forward"
CHECKPOINT_TABLE = "l2f_historical_replay_checkpoints"
EVAL_TABLE = "l2f_shadow_evaluations"

CHECKPOINT_DDL = f"""
CREATE TABLE IF NOT EXISTS {CHECKPOINT_TABLE} (
    checkpoint_id TEXT PRIMARY KEY,
    run_label TEXT NOT NULL,
    last_fixture_id INTEGER,
    processed INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    blocked INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    updated_at_utc TEXT NOT NULL
)
"""

EVAL_DDL = f"""
CREATE TABLE IF NOT EXISTS {EVAL_TABLE} (
    eval_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    freeze_id TEXT,
    model_id TEXT NOT NULL,
    model_version TEXT,
    run_id TEXT NOT NULL,
    cohort_type TEXT NOT NULL,
    actual_home INTEGER,
    actual_away INTEGER,
    lambda_home REAL,
    lambda_away REAL,
    lambda_home_err REAL,
    lambda_away_err REAL,
    lambda_total_err REAL,
    top1 INTEGER,
    top3 INTEGER,
    top5 INTEGER,
    top10 INTEGER,
    log_loss REAL,
    actual_rank INTEGER,
    p_actual REAL,
    canonical_top5 INTEGER,
    input_hash TEXT,
    output_hash TEXT,
    created_at_utc TEXT NOT NULL,
    UNIQUE(fixture_id, freeze_id, model_id, run_id)
)
"""


@dataclass
class ReplayBatchResult:
    dry_run: bool
    cohort_type: str
    processed: int = 0
    success: int = 0
    skipped: int = 0
    blocked: int = 0
    failed: int = 0
    fixture_ids: list[int] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    disk_before: str | None = None
    disk_after: str | None = None
    stopped_reason: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def ensure_replay_schema(fi_conn: sqlite3.Connection) -> None:
    ensure_job_schema(fi_conn)
    fi_conn.execute(CHECKPOINT_DDL)
    fi_conn.execute(EVAL_DDL)
    fi_conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_eval_fx ON {EVAL_TABLE}(fixture_id)")
    fi_conn.execute(f"CREATE INDEX IF NOT EXISTS idx_l2f_eval_cohort ON {EVAL_TABLE}(cohort_type)")
    fi_conn.commit()


def _settings_flags(settings: Any | None) -> dict[str, Any]:
    if settings is None:
        try:
            from worldcup_predictor.config.settings import get_settings

            settings = get_settings()
        except Exception:
            return {"kill_switch": False, "mode": "shadow", "fi_path": "data/football_intelligence.db"}
    return {
        "kill_switch": bool(getattr(settings, "l2f_forward_shadow_kill_switch", False)),
        "mode": str(getattr(settings, "l2f_forward_shadow_mode", "shadow") or "shadow"),
        "fi_path": str(getattr(settings, "sqlite_path", "data/football_intelligence.db")),
    }


def free_gb_from_df_line(line: str) -> float | None:
    # Expect: Filesystem Size Used Avail Use% Mounted
    parts = line.split()
    if len(parts) < 4:
        return None
    avail = parts[3]
    try:
        if avail.endswith("G"):
            return float(avail[:-1])
        if avail.endswith("M"):
            return float(avail[:-1]) / 1024.0
        if avail.endswith("T"):
            return float(avail[:-1]) * 1024.0
        return float(avail)
    except Exception:
        return None


def run_historical_replay_batch(
    *,
    eval_conn: sqlite3.Connection,
    fi_conn: sqlite3.Connection,
    batch_size: int = 20,
    dry_run: bool = True,
    cohort: str = COHORT_HISTORICAL,
    settings: Any | None = None,
    min_free_gb: float = 8.0,
    disk_line: str | None = None,
    resume_after_fixture_id: int | None = None,
    run_label: str = "l2f-hist-replay",
    integrity_hooks: list[Callable[[FreezeCandidate, dict[str, Any]], str | None]] | None = None,
) -> ReplayBatchResult:
    """
    Bounded batch replay. Never mutates freezes/results.
    """
    flags = _settings_flags(settings)
    out = ReplayBatchResult(dry_run=dry_run, cohort_type=cohort, disk_before=disk_line)
    if flags["kill_switch"]:
        out.stopped_reason = "kill_switch"
        return out
    if flags["mode"] != "shadow":
        out.stopped_reason = f"mode_{flags['mode']}"
        return out

    free = free_gb_from_df_line(disk_line) if disk_line else None
    if free is not None and free < min_free_gb:
        out.stopped_reason = f"disk_free_below_{min_free_gb}G"
        return out

    ensure_replay_schema(fi_conn)
    candidates = inventory_eval_db(eval_conn)
    wanted = CLASS_ELIGIBLE_HISTORICAL if cohort == COHORT_HISTORICAL else CLASS_ELIGIBLE_TRUE_FORWARD
    eligible = [c for c in candidates if c.classification == wanted and c.is_first_for_fixture]
    if resume_after_fixture_id is not None:
        eligible = [c for c in eligible if c.fixture_id > int(resume_after_fixture_id)]
    batch = eligible[: max(0, int(batch_size))]

    for c in batch:
        out.processed += 1
        out.fixture_ids.append(c.fixture_id)
        detail: dict[str, Any] = {
            "fixture_id": c.fixture_id,
            "freeze_id": c.freeze_id,
            "cohort_type": cohort,
            "classification": c.classification,
        }
        # Leakage pre-check
        fr = c.frozen_at
        ko = c.kickoff
        if fr and ko and fr.replace(" ", "T") >= ko.replace(" ", "T"):
            detail["status"] = "blocked"
            detail["reason"] = "frozen_at_not_before_kickoff"
            out.blocked += 1
            out.details.append(detail)
            continue

        if dry_run:
            detail["status"] = "dry_run_eligible"
            out.skipped += 1
            out.details.append(detail)
            continue

        freeze_meta = {
            "capture_status": "reused",
            "freeze_id": c.freeze_id,
            "prediction_scope": c.prediction_scope or "owner_shadow",
            "quarantined": False,
            "conflict_detected": False,
            "cohort_type": cohort,
            "frozen_at": c.frozen_at,
            "kickoff": c.kickoff,
            "canonical_lambda_home": c.lambda_home,
            "canonical_lambda_away": c.lambda_away,
        }
        meta = maybe_run_l2f_forward_shadow(
            conn=fi_conn,
            fixture_id=c.fixture_id,
            freeze_meta=freeze_meta,
            prediction_scope=c.prediction_scope or "owner_shadow",
            settings=settings,
            backfill=True,
        )
        detail["shadow"] = {
            "status": meta.get("status"),
            "reason": meta.get("reason"),
            "lambda_rows": meta.get("lambda_rows"),
            "exact_rows": meta.get("exact_rows"),
            "run_id": meta.get("run_id"),
        }
        st = str(meta.get("status") or "failed")
        if st == "success":
            out.success += 1
            if c.has_result and c.actual_home is not None and c.actual_away is not None:
                evaluate_shadow_against_result(
                    fi_conn,
                    fixture_id=c.fixture_id,
                    freeze_id=c.freeze_id,
                    run_id=str(meta.get("run_id") or "l2f-forward-v1-backfill"),
                    cohort_type=cohort,
                    actual_home=int(c.actual_home),
                    actual_away=int(c.actual_away),
                    canonical_top5=_canonical_top5_hit(eval_conn, c.freeze_id),
                )
        elif st == "skipped":
            out.skipped += 1
        elif st == "blocked":
            out.blocked += 1
        else:
            out.failed += 1

        if integrity_hooks:
            for hook in integrity_hooks:
                anomaly = hook(c, meta)
                if anomaly:
                    out.stopped_reason = anomaly
                    out.details.append(detail)
                    _save_checkpoint(fi_conn, run_label, c.fixture_id, out)
                    return out

        out.details.append(detail)
        _save_checkpoint(fi_conn, run_label, c.fixture_id, out)

    return out


def _save_checkpoint(fi_conn: sqlite3.Connection, run_label: str, last_fx: int, out: ReplayBatchResult) -> None:
    ensure_replay_schema(fi_conn)
    cid = f"ckpt-{run_label}"
    fi_conn.execute(
        f"""
        INSERT INTO {CHECKPOINT_TABLE} (
            checkpoint_id, run_label, last_fixture_id, processed, success, skipped, blocked, failed, updated_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(checkpoint_id) DO UPDATE SET
            last_fixture_id=excluded.last_fixture_id,
            processed=excluded.processed,
            success=excluded.success,
            skipped=excluded.skipped,
            blocked=excluded.blocked,
            failed=excluded.failed,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            cid,
            run_label,
            int(last_fx),
            out.processed,
            out.success,
            out.skipped,
            out.blocked,
            out.failed,
            _now(),
        ),
    )
    fi_conn.commit()


def _canonical_top5_hit(eval_conn: sqlite3.Connection, freeze_id: str) -> int | None:
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


def evaluate_shadow_against_result(
    fi_conn: sqlite3.Connection,
    *,
    fixture_id: int,
    freeze_id: str | None,
    run_id: str,
    cohort_type: str,
    actual_home: int,
    actual_away: int,
    canonical_top5: int | None = None,
) -> int:
    """Score L2-F shadow rows vs FT result. Additive only."""
    from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE
    from worldcup_predictor.research.football_strength_foundation.score_v2 import dist_poisson, exact_metrics

    ensure_replay_schema(fi_conn)
    rows = fi_conn.execute(
        f"""
        SELECT model_id, model_version, lambda_home, lambda_away, top10_json, shadow_hash, payload_json
        FROM {SHADOW_TABLE}
        WHERE fixture_id=?
        """,
        (int(fixture_id),),
    ).fetchall()
    n = 0
    ah, aa = int(actual_home), int(actual_away)
    total_goals = ah + aa
    for r in rows:
        model_id = r[0] if not isinstance(r, sqlite3.Row) else r["model_id"]
        model_version = r[1] if not isinstance(r, sqlite3.Row) else r["model_version"]
        lh = r[2] if not isinstance(r, sqlite3.Row) else r["lambda_home"]
        la = r[3] if not isinstance(r, sqlite3.Row) else r["lambda_away"]
        top10_json = r[4] if not isinstance(r, sqlite3.Row) else r["top10_json"]
        shadow_hash = r[5] if not isinstance(r, sqlite3.Row) else r["shadow_hash"]
        if lh is None or la is None:
            continue
        lh_f, la_f = float(lh), float(la)
        dist = dist_poisson(lh_f, la_f)
        em = exact_metrics(dist, ah, aa)
        home_err = abs(lh_f - ah)
        away_err = abs(la_f - aa)
        total_err = abs((lh_f + la_f) - total_goals)
        input_hash = hashlib.sha256(
            json.dumps(
                {"fixture_id": fixture_id, "freeze_id": freeze_id, "model_id": model_id, "cohort": cohort_type},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        eval_id = f"ev-{fixture_id}-{model_id}-{run_id}-{shadow_hash[:10]}"
        fi_conn.execute(
            f"""
            INSERT OR IGNORE INTO {EVAL_TABLE} (
                eval_id, fixture_id, freeze_id, model_id, model_version, run_id, cohort_type,
                actual_home, actual_away, lambda_home, lambda_away,
                lambda_home_err, lambda_away_err, lambda_total_err,
                top1, top3, top5, top10, log_loss, actual_rank, p_actual,
                canonical_top5, input_hash, output_hash, created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                eval_id,
                int(fixture_id),
                freeze_id,
                model_id,
                model_version,
                run_id,
                cohort_type,
                ah,
                aa,
                lh_f,
                la_f,
                home_err,
                away_err,
                total_err,
                int(em["top1"]),
                int(em["top3"]),
                int(em["top5"]),
                int(em["top10"]),
                float(em["log_loss"]),
                em["rank"],
                em["p_actual"],
                canonical_top5,
                input_hash,
                shadow_hash,
                _now(),
            ),
        )
        n += 1
    fi_conn.commit()
    return n


def aggregate_eval_metrics(fi_conn: sqlite3.Connection, *, cohort_type: str | None = None) -> dict[str, Any]:
    ensure_replay_schema(fi_conn)
    where = "WHERE cohort_type=?" if cohort_type else ""
    params: tuple[Any, ...] = (cohort_type,) if cohort_type else ()
    rows = fi_conn.execute(
        f"""
        SELECT model_id,
               COUNT(*) AS n,
               AVG(lambda_total_err) AS mae_total,
               AVG(lambda_home_err) AS mae_home,
               AVG(lambda_away_err) AS mae_away,
               AVG(top1) AS top1,
               AVG(top3) AS top3,
               AVG(top5) AS top5,
               AVG(top10) AS top10,
               AVG(log_loss) AS log_loss,
               AVG(canonical_top5) AS canonical_top5
        FROM {EVAL_TABLE}
        {where}
        GROUP BY model_id
        ORDER BY model_id
        """,
        params,
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "model_id": r[0],
                "n": r[1],
                "mae_total": r[2],
                "mae_home": r[3],
                "mae_away": r[4],
                "top1": r[5],
                "top3": r[6],
                "top5": r[7],
                "top10": r[8],
                "log_loss": r[9],
                "canonical_top5": r[10],
            }
        )
    return {"cohort_type": cohort_type or "combined", "models": out}
