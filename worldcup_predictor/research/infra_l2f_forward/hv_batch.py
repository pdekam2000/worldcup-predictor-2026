"""Phase 6 — bounded high-volume true-forward batch orchestration.

Canonical predict → immutable freeze → shadow (isolated). Disk stop <8G.
Idempotent, resumable, never promotes challengers.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from worldcup_predictor.research.infra_l2f_forward.diversity_sampling import (
    DEFAULT_DAILY_CAP,
    DEFAULT_SEED,
    SAMPLING_POLICY_VERSION,
    sample_eligible_fixtures,
)
from worldcup_predictor.research.infra_l2f_forward.daily_universe import (
    build_daily_universe,
    eligible_rows,
)
from worldcup_predictor.research.infra_l2f_forward.historical_replay import free_gb_from_df_line
from worldcup_predictor.research.infra_l2f_forward.result_recovery import df_line

logger = logging.getLogger(__name__)

CHECKPOINT_TABLE = "l2f_hv_tf_checkpoints"
BATCH_ITEM_TABLE = "l2f_hv_tf_batch_items"
DEFAULT_MIN_FREE_GB = 8.0
DEFAULT_ALERT_FREE_GB = 10.0
DEFAULT_FIXTURE_TIMEOUT_SEC = 600.0
STAGE_CAPS = (20, 50, 100)

CHECKPOINT_DDL = f"""
CREATE TABLE IF NOT EXISTS {CHECKPOINT_TABLE} (
    checkpoint_id TEXT PRIMARY KEY,
    vienna_date TEXT NOT NULL,
    stage TEXT NOT NULL,
    daily_cap INTEGER NOT NULL,
    sampling_policy_version TEXT NOT NULL,
    seed TEXT NOT NULL,
    dry_run INTEGER NOT NULL DEFAULT 1,
    last_fixture_id INTEGER,
    processed INTEGER NOT NULL DEFAULT 0,
    canonical_success INTEGER NOT NULL DEFAULT 0,
    canonical_blocked INTEGER NOT NULL DEFAULT 0,
    canonical_failed INTEGER NOT NULL DEFAULT 0,
    shadow_success INTEGER NOT NULL DEFAULT 0,
    shadow_failed INTEGER NOT NULL DEFAULT 0,
    shadow_skipped INTEGER NOT NULL DEFAULT 0,
    stopped_reason TEXT,
    artifact_dir TEXT,
    updated_at_utc TEXT NOT NULL,
    payload_json TEXT
)
"""

ITEM_DDL = f"""
CREATE TABLE IF NOT EXISTS {BATCH_ITEM_TABLE} (
    item_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL,
    fixture_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    canonical_status TEXT,
    freeze_id TEXT,
    freeze_hash TEXT,
    shadow_status TEXT,
    shadow_job_id TEXT,
    cohort_type TEXT,
    reason TEXT,
    duration_ms REAL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(checkpoint_id, fixture_id)
)
"""


@dataclass
class HvBatchResult:
    dry_run: bool
    vienna_date: str
    stage: str
    daily_cap: int
    checkpoint_id: str
    discovered: int = 0
    eligible: int = 0
    selected: int = 0
    processed: int = 0
    canonical_success: int = 0
    canonical_blocked: int = 0
    canonical_failed: int = 0
    shadow_success: int = 0
    shadow_failed: int = 0
    shadow_skipped: int = 0
    stopped_reason: str | None = None
    disk_before: str | None = None
    disk_after: str | None = None
    disk_alert: bool = False
    artifact_dir: str | None = None
    sampling: dict[str, Any] = field(default_factory=dict)
    universe_summary: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    promotion_occurred: bool = False
    routing_activation_occurred: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "vienna_date": self.vienna_date,
            "stage": self.stage,
            "daily_cap": self.daily_cap,
            "checkpoint_id": self.checkpoint_id,
            "discovered": self.discovered,
            "eligible": self.eligible,
            "selected": self.selected,
            "processed": self.processed,
            "canonical_success": self.canonical_success,
            "canonical_blocked": self.canonical_blocked,
            "canonical_failed": self.canonical_failed,
            "shadow_success": self.shadow_success,
            "shadow_failed": self.shadow_failed,
            "shadow_skipped": self.shadow_skipped,
            "stopped_reason": self.stopped_reason,
            "disk_before": self.disk_before,
            "disk_after": self.disk_after,
            "disk_alert": self.disk_alert,
            "artifact_dir": self.artifact_dir,
            "sampling": self.sampling,
            "universe_summary": self.universe_summary,
            "items": self.items,
            "promotion_occurred": self.promotion_occurred,
            "routing_activation_occurred": self.routing_activation_occurred,
            "explicit": "No promotion and no routing activation occurred.",
        }


def ensure_hv_schema(conn: sqlite3.Connection) -> None:
    conn.execute(CHECKPOINT_DDL)
    conn.execute(ITEM_DDL)
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_l2f_hv_items_cp ON {BATCH_ITEM_TABLE}(checkpoint_id)"
    )
    conn.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def stage_name_for_cap(daily_cap: int, *, dry_run: bool) -> str:
    if dry_run:
        return "stage1_dry_run"
    if daily_cap <= 20:
        return "stage2_cap20"
    if daily_cap <= 50:
        return "stage3_cap50"
    return "stage4_cap100"


def default_fixture_processor(ctx: dict[str, Any]) -> dict[str, Any]:
    """Process one selected fixture: canonical → freeze → L2F shadow.

    Isolated failures never mutate promotion flags.
    """
    from worldcup_predictor.research.infra_l2f_forward.hv_fixture_executor import (
        process_true_forward_fixture,
    )

    return process_true_forward_fixture(**ctx)


def run_hv_true_forward_day(
    *,
    vienna_date: str,
    daily_cap: int = DEFAULT_DAILY_CAP,
    dry_run: bool = True,
    seed: str = DEFAULT_SEED,
    sampling_policy_version: str = SAMPLING_POLICY_VERSION,
    prod_conn: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
    fi_conn: sqlite3.Connection,
    settings: Any | None = None,
    artifact_root: Path | None = None,
    min_free_gb: float = DEFAULT_MIN_FREE_GB,
    alert_free_gb: float = DEFAULT_ALERT_FREE_GB,
    fixture_timeout_sec: float = DEFAULT_FIXTURE_TIMEOUT_SEC,
    resume_checkpoint_id: str | None = None,
    fixture_processor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    require_fresh_odds_for_eligibility: bool = False,
    scope: str = "owner",
) -> HvBatchResult:
    ensure_hv_schema(fi_conn)
    stage = stage_name_for_cap(int(daily_cap), dry_run=dry_run)
    disk_before = df_line()
    free = free_gb_from_df_line(disk_before)
    checkpoint_id = resume_checkpoint_id or f"hvtf-{vienna_date}-{stage}-{uuid.uuid4().hex[:10]}"

    base = Path(artifact_root) if artifact_root else Path("artifacts") / "phase6_hv_tf" / vienna_date
    art = base / checkpoint_id
    art.mkdir(parents=True, exist_ok=True)

    out = HvBatchResult(
        dry_run=dry_run,
        vienna_date=vienna_date,
        stage=stage,
        daily_cap=int(daily_cap),
        checkpoint_id=checkpoint_id,
        disk_before=disk_before,
        artifact_dir=str(art),
        disk_alert=bool(free is not None and free < float(alert_free_gb)),
    )

    if free is not None and free < float(min_free_gb):
        out.stopped_reason = f"disk_free_below_{min_free_gb}G"
        _persist_checkpoint(fi_conn, out)
        _write_json(art / "batch_result.json", out.to_dict())
        return out

    universe = build_daily_universe(
        target_date=vienna_date,
        scope=scope,
        prod_conn=prod_conn,
        eval_conn=eval_conn,
        fi_conn=fi_conn,
        require_fresh_odds_for_eligibility=require_fresh_odds_for_eligibility,
    )
    _write_json(art / "universe.json", universe)
    eligible = eligible_rows(universe)
    sampling = sample_eligible_fixtures(
        eligible,
        daily_cap=int(daily_cap),
        seed=seed,
        policy_version=sampling_policy_version,
    )
    _write_json(art / "sampling.json", sampling)

    out.discovered = int(universe.get("discovered_count") or 0)
    out.eligible = int(universe.get("eligible_count") or 0)
    out.selected = int(sampling.get("selected_count") or 0)
    out.sampling = {
        "sampling_policy_version": sampling.get("sampling_policy_version"),
        "seed": sampling.get("seed"),
        "daily_cap": sampling.get("daily_cap"),
        "selected_fixture_ids": sampling.get("selected_fixture_ids"),
        "non_selected_eligible_fixture_ids": sampling.get("non_selected_eligible_fixture_ids"),
        "reproducibility": sampling.get("reproducibility"),
        "league_distribution": sampling.get("league_distribution"),
        "odds_strength_distribution": sampling.get("odds_strength_distribution"),
        "market_balance_distribution": sampling.get("market_balance_distribution"),
        "expected_total_distribution": sampling.get("expected_total_distribution"),
    }
    out.universe_summary = {
        "discovered_count": out.discovered,
        "eligible_count": out.eligible,
        "excluded_count": universe.get("excluded_count"),
        "exclusion_counts": universe.get("exclusion_counts"),
        "eligible_by_league": universe.get("eligible_by_league"),
    }

    already_done = _loaded_done_fixture_ids(fi_conn, checkpoint_id) if resume_checkpoint_id else set()
    processor = fixture_processor or default_fixture_processor
    selected_rows = list(sampling.get("selected") or [])

    for row in selected_rows:
        fid = int(row["fixture_id"])
        if fid in already_done:
            continue

        free_now = free_gb_from_df_line(df_line())
        if free_now is not None and free_now < float(min_free_gb):
            out.stopped_reason = f"disk_free_below_{min_free_gb}G_mid_batch"
            break
        if free_now is not None and free_now < float(alert_free_gb):
            out.disk_alert = True

        item: dict[str, Any] = {
            "fixture_id": fid,
            "competition_key": row.get("competition_key"),
            "kickoff_utc": row.get("kickoff_utc"),
        }
        t0 = time.perf_counter()

        if dry_run:
            item.update(
                {
                    "status": "dry_run_selected",
                    "canonical_status": "dry_run",
                    "shadow_status": "dry_run",
                    "cohort_type": "true_forward",
                    "reason": "stage1_no_prediction_writes",
                }
            )
            out.processed += 1
            out.items.append(item)
            _upsert_item(fi_conn, checkpoint_id, item, duration_ms=(time.perf_counter() - t0) * 1000)
            _persist_checkpoint(fi_conn, out, last_fixture_id=fid)
            continue

        ctx = {
            "fixture_id": fid,
            "fixture_row": row,
            "prod_conn": prod_conn,
            "eval_conn": eval_conn,
            "fi_conn": fi_conn,
            "settings": settings,
            "prediction_scope": row.get("prediction_scope") or "owner_shadow",
        }
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(processor, ctx)
                result = fut.result(timeout=float(fixture_timeout_sec))
        except FuturesTimeout:
            result = {
                "status": "failed",
                "canonical_status": "timeout",
                "shadow_status": "not_run",
                "reason": "per_fixture_timeout",
            }
        except Exception as exc:  # noqa: BLE001
            result = {
                "status": "failed",
                "canonical_status": "exception",
                "shadow_status": "not_run",
                "reason": f"{type(exc).__name__}:{exc}",
                "traceback": traceback.format_exc()[-1500:],
            }

        item.update(result)
        dur = (time.perf_counter() - t0) * 1000
        item["duration_ms"] = dur
        out.processed += 1

        cs = str(result.get("canonical_status") or "")
        if cs in {"success", "reused_freeze", "created", "reused"}:
            out.canonical_success += 1
        elif cs in {"blocked", "odds_blocked", "quality_gate", "post_kickoff"}:
            out.canonical_blocked += 1
        elif cs not in {"dry_run"}:
            out.canonical_failed += 1

        ss = str(result.get("shadow_status") or "")
        if ss in {"success", "already_success_idempotent"}:
            out.shadow_success += 1
        elif ss in {"skipped", "blocked"}:
            out.shadow_skipped += 1
        elif ss not in {"dry_run", "not_run", ""}:
            out.shadow_failed += 1

        out.items.append(item)
        _upsert_item(fi_conn, checkpoint_id, item, duration_ms=dur)
        _persist_checkpoint(fi_conn, out, last_fixture_id=fid)

    out.disk_after = df_line()
    _persist_checkpoint(fi_conn, out)
    _write_json(art / "batch_result.json", out.to_dict())
    _write_json(art / "items.json", out.items)
    return out


def _persist_checkpoint(
    conn: sqlite3.Connection,
    out: HvBatchResult,
    *,
    last_fixture_id: int | None = None,
) -> None:
    ensure_hv_schema(conn)
    conn.execute(
        f"""
        INSERT INTO {CHECKPOINT_TABLE} (
            checkpoint_id, vienna_date, stage, daily_cap, sampling_policy_version, seed,
            dry_run, last_fixture_id, processed, canonical_success, canonical_blocked,
            canonical_failed, shadow_success, shadow_failed, shadow_skipped, stopped_reason,
            artifact_dir, updated_at_utc, payload_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(checkpoint_id) DO UPDATE SET
            last_fixture_id=excluded.last_fixture_id,
            processed=excluded.processed,
            canonical_success=excluded.canonical_success,
            canonical_blocked=excluded.canonical_blocked,
            canonical_failed=excluded.canonical_failed,
            shadow_success=excluded.shadow_success,
            shadow_failed=excluded.shadow_failed,
            shadow_skipped=excluded.shadow_skipped,
            stopped_reason=excluded.stopped_reason,
            artifact_dir=excluded.artifact_dir,
            updated_at_utc=excluded.updated_at_utc,
            payload_json=excluded.payload_json
        """,
        (
            out.checkpoint_id,
            out.vienna_date,
            out.stage,
            out.daily_cap,
            (out.sampling or {}).get("sampling_policy_version") or SAMPLING_POLICY_VERSION,
            (out.sampling or {}).get("seed") or DEFAULT_SEED,
            1 if out.dry_run else 0,
            last_fixture_id,
            out.processed,
            out.canonical_success,
            out.canonical_blocked,
            out.canonical_failed,
            out.shadow_success,
            out.shadow_failed,
            out.shadow_skipped,
            out.stopped_reason,
            out.artifact_dir,
            _utc_now(),
            json.dumps(
                {
                    "universe_summary": out.universe_summary,
                    "sampling_ids": (out.sampling or {}).get("selected_fixture_ids"),
                    "promotion_occurred": False,
                    "routing_activation_occurred": False,
                },
                default=str,
            ),
        ),
    )
    conn.commit()


def _upsert_item(
    conn: sqlite3.Connection,
    checkpoint_id: str,
    item: dict[str, Any],
    *,
    duration_ms: float | None = None,
) -> None:
    ensure_hv_schema(conn)
    item_id = f"{checkpoint_id}:{int(item['fixture_id'])}"
    conn.execute(
        f"""
        INSERT INTO {BATCH_ITEM_TABLE} (
            item_id, checkpoint_id, fixture_id, status, canonical_status, freeze_id,
            freeze_hash, shadow_status, shadow_job_id, cohort_type, reason, duration_ms,
            updated_at_utc
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(checkpoint_id, fixture_id) DO UPDATE SET
            status=excluded.status,
            canonical_status=excluded.canonical_status,
            freeze_id=excluded.freeze_id,
            freeze_hash=excluded.freeze_hash,
            shadow_status=excluded.shadow_status,
            shadow_job_id=excluded.shadow_job_id,
            cohort_type=excluded.cohort_type,
            reason=excluded.reason,
            duration_ms=excluded.duration_ms,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            item_id,
            checkpoint_id,
            int(item["fixture_id"]),
            str(item.get("status") or "unknown"),
            item.get("canonical_status"),
            item.get("freeze_id"),
            item.get("freeze_hash"),
            item.get("shadow_status"),
            item.get("shadow_job_id"),
            item.get("cohort_type") or "true_forward",
            item.get("reason"),
            duration_ms if duration_ms is not None else item.get("duration_ms"),
            _utc_now(),
        ),
    )
    conn.commit()


def _loaded_done_fixture_ids(conn: sqlite3.Connection, checkpoint_id: str) -> set[int]:
    ensure_hv_schema(conn)
    rows = conn.execute(
        f"""
        SELECT fixture_id FROM {BATCH_ITEM_TABLE}
        WHERE checkpoint_id=? AND status NOT IN ('failed')
        """,
        (checkpoint_id,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def promotion_gate_for_next_stage(
    *,
    canonical_success: int,
    canonical_attempted: int,
    shadow_success: int,
    shadow_attempted: int,
    freeze_mutations: int = 0,
    disk_free_gb: float | None = None,
    min_free_gb: float = DEFAULT_MIN_FREE_GB,
    min_shadow_success_rate: float = 0.98,
    min_canonical_success_rate: float = 0.90,
) -> dict[str, Any]:
    """Whether the next batch-size stage may proceed (still no promotion of models)."""
    can_rate = (canonical_success / canonical_attempted) if canonical_attempted else 1.0
    sh_rate = (shadow_success / shadow_attempted) if shadow_attempted else 1.0
    disk_ok = disk_free_gb is None or disk_free_gb >= min_free_gb
    ok = (
        can_rate >= min_canonical_success_rate
        and sh_rate >= min_shadow_success_rate
        and freeze_mutations == 0
        and disk_ok
    )
    return {
        "may_increase_cap": ok,
        "canonical_success_rate": can_rate,
        "shadow_success_rate": sh_rate,
        "freeze_mutations": freeze_mutations,
        "disk_ok": disk_ok,
        "model_promotion_allowed": False,
        "routing_activation_allowed": False,
        "note": "Cap increase is operational only; challengers remain SHADOW_RESEARCH_ONLY.",
    }
