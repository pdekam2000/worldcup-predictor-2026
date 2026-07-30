"""Per-fixture true-forward executor for Phase 6 HV batch.

Canonical prediction + immutable freeze first; L2F shadow only after freeze.
Never promotes. Failures are isolated from canonical persistence.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.bridge import (
    ForwardEvalBridgeContext,
    maybe_capture_after_prediction_persistence,
)
from worldcup_predictor.gpt_actions.config import GptActionsConfig, load_gpt_actions_config
from worldcup_predictor.gpt_actions.job_status import build_job_status_fields
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.owner_scope import fixture_tier
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.worker import enqueue_prediction_job
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow

FRESH_OK = frozenset({FreshnessStatus.FRESH_ODDS.value, "fresh", "ODDS_FRESH", "FRESH_ODDS"})
PREMATCH = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", ""})


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _load_freeze(eval_conn, fid: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        """
        SELECT prediction_id, content_hash, source_payload_hash, frozen_at, freeze_status,
               prediction_scope, lambda_home, lambda_away, kickoff
        FROM frozen_predictions
        WHERE fixture_id=? AND IFNULL(freeze_status,'ACTIVE')='ACTIVE'
        ORDER BY frozen_at ASC
        LIMIT 1
        """,
        (int(fid),),
    ).fetchone()
    return dict(row) if row else None


def _poll(job_id: str, store: JobStore, cfg: GptActionsConfig, deadline_s: int = 540) -> dict[str, Any]:
    final = None
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        rec = store.get(job_id)
        if not rec or not rec.get("job_id"):
            time.sleep(1)
            continue
        fields = build_job_status_fields(rec, poll_after_seconds=cfg.poll_after_seconds)
        if fields.get("terminal"):
            final = {**rec, **fields}
            break
        time.sleep(max(1, int(fields.get("poll_after_seconds") or 3)))
    return {"final": final, "timed_out": final is None}


def _run_shadow(*, prod_conn, fixture_id: int, freeze_meta: dict[str, Any], prediction_scope: str | None, settings) -> dict[str, Any]:
    try:
        meta = dict(freeze_meta or {})
        cs = str(meta.get("capture_status") or "")
        if cs in ("reused_existing", "reused"):
            meta["capture_status"] = "reused"
        elif meta.get("created"):
            meta["capture_status"] = "created"
        elif meta.get("reused"):
            meta["capture_status"] = "reused"
        if not meta.get("prediction_scope") and prediction_scope:
            meta["prediction_scope"] = prediction_scope
        return maybe_run_l2f_forward_shadow(
            conn=prod_conn,
            fixture_id=int(fixture_id),
            freeze_meta=meta,
            prediction_scope=prediction_scope or meta.get("prediction_scope"),
            settings=settings,
            backfill=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "shadow_system": "l2f_forward",
            "canonical_unaffected": True,
            "status": "failed",
            "reason": f"hook_exception:{type(exc).__name__}",
            "cohort_type": "true_forward",
        }


def process_true_forward_fixture(
    *,
    fixture_id: int,
    fixture_row: dict[str, Any] | None = None,
    prod_conn: Any = None,
    eval_conn: Any = None,
    fi_conn: Any = None,  # noqa: ARG001 — reserved for future job annotations
    settings: Any | None = None,
    prediction_scope: str | None = None,
    job_store_dir: str | Path | None = None,
    poll_deadline_s: int = 540,
) -> dict[str, Any]:
    """Execute one fixture end-to-end for HV true-forward collection."""
    bootstrap_gpt_actions_runtime()
    settings = settings or get_settings()
    fid = int(fixture_id)
    row = dict(fixture_row or {})

    # Re-open connections if callers passed closed handles (ThreadPool safety).
    prod = prod_conn if prod_conn is not None else connect(settings.sqlite_path)
    eval_db = eval_conn
    if eval_db is None:
        from worldcup_predictor.forward_evaluation.db import connect_eval_db

        eval_db = connect_eval_db()

    fx = prod.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, competition_key, season
        FROM fixtures WHERE fixture_id=?
        """,
        (fid,),
    ).fetchone()
    if not fx and not row.get("kickoff_utc"):
        return {
            "status": "blocked",
            "canonical_status": "blocked",
            "shadow_status": "not_run",
            "reason": "fixture_not_found",
            "cohort_type": "true_forward",
        }

    home = str((fx["home_team"] if fx else None) or row.get("home_team") or "TBD")
    away = str((fx["away_team"] if fx else None) or row.get("away_team") or "TBD")
    ko = str((fx["kickoff_utc"] if fx else None) or row.get("kickoff_utc") or "")
    status = str((fx["status"] if fx else None) or row.get("status") or "NS").upper()
    comp = str((fx["competition_key"] if fx else None) or row.get("competition_key") or "")
    scope = prediction_scope or row.get("prediction_scope") or (
        "production" if (fixture_tier(comp) == "A") else "owner_shadow"
    )

    ko_dt = _parse_dt(ko)
    now = datetime.now(timezone.utc)
    if ko_dt and now >= ko_dt:
        return {
            "status": "blocked",
            "canonical_status": "post_kickoff",
            "shadow_status": "not_run",
            "reason": "already_started",
            "cohort_type": "true_forward",
        }
    if status not in PREMATCH:
        return {
            "status": "blocked",
            "canonical_status": "blocked",
            "shadow_status": "not_run",
            "reason": f"status_{status}",
            "cohort_type": "true_forward",
        }

    existing = _load_freeze(eval_db, fid)
    pred_exists = prod.execute(
        "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
    ).fetchone()
    snap = get_snapshot(prod, fid)

    freeze_meta: dict[str, Any] = {}
    mode = "NEW_PREDICTION"

    if existing and pred_exists and snap:
        mode = "REUSE_IMMUTABLE_FREEZE"
        freeze_meta = {
            "freeze_id": existing.get("prediction_id"),
            "prediction_id": existing.get("prediction_id"),
            "content_hash": existing.get("content_hash"),
            "source_payload_hash": existing.get("source_payload_hash"),
            "frozen_at": existing.get("frozen_at"),
            "prediction_scope": existing.get("prediction_scope") or scope,
            "capture_status": "reused",
            "reused": True,
            "kickoff_utc": existing.get("kickoff") or ko,
            "lambda_home": existing.get("lambda_home"),
            "lambda_away": existing.get("lambda_away"),
        }
        hash_before = existing.get("content_hash")
    else:
        if not mcp_runtime.model_status().get("canonical_pipeline_ready"):
            return {
                "status": "blocked",
                "canonical_status": "quality_gate",
                "shadow_status": "not_run",
                "reason": "canonical_pipeline_not_ready",
                "cohort_type": "true_forward",
            }

        daily = DailyFixture(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition_key=comp,
            home_team=home,
            away_team=away,
            kickoff_utc=ko,
            status=status,
            season=int(fx["season"]) if fx and fx["season"] is not None else None,
        )
        refresh_live_odds(daily, settings=settings)
        # Refresh connection after odds write
        if prod_conn is None:
            try:
                prod.close()
            except Exception:
                pass
            prod = connect(settings.sqlite_path)

        gate = ensure_fresh_odds_before_prediction(
            prod,
            {"fixture_id": fid, "kickoff_utc": ko, "status": status},
            daily,
            settings=settings,
            refresh_if_needed=True,
        )
        odds = get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=ko)
        fresh_flag = bool(gate.get("allowed"))
        if odds is not None:
            fr = getattr(odds, "freshness_class", None) or getattr(odds, "freshness_status", None)
            fresh_flag = fresh_flag and (str(fr or "") in FRESH_OK or bool(gate.get("allowed")))
        if not fresh_flag or odds is None:
            return {
                "status": "blocked",
                "canonical_status": "odds_blocked",
                "shadow_status": "not_run",
                "reason": str(gate.get("final_block_reason") or gate.get("reason") or "stale_or_missing_odds"),
                "cohort_type": "true_forward",
            }

        art = Path(job_store_dir or Path("artifacts") / "phase6_hv_tf" / "jobs")
        art.mkdir(parents=True, exist_ok=True)
        base_cfg = load_gpt_actions_config()
        cfg = GptActionsConfig(
            host=base_cfg.host,
            port=base_cfg.port,
            api_key=base_cfg.api_key,
            audit_log_path=str(art / "audit.jsonl"),
            job_store_dir=str(art),
            max_jobs_retained=200,
            rate_limit_per_minute=base_cfg.rate_limit_per_minute,
            max_fixture_ids_per_job=base_cfg.max_fixture_ids_per_job,
            max_response_chars=base_cfg.max_response_chars,
            poll_after_seconds=base_cfg.poll_after_seconds,
        )
        store = JobStore(str(art), max_retained=200)
        job_id = str(uuid.uuid4())
        record = {
            "job_id": job_id,
            "status": "queued",
            "run_id": f"phase6-hv-{_utc_now()}",
            "created_at": _utc_now(),
            "request": {
                "scope": "owner",
                "prediction_scope": scope,
                "fixture_ids": [fid],
                "refresh_if_stale": True,
                "include_all_predictions": True,
            },
        }
        store._path(job_id).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        enqueue_prediction_job(job_id, store=store, config=cfg)
        poll = _poll(job_id, store, cfg, deadline_s=poll_deadline_s)
        final = poll.get("final") or store.get(job_id) or {}
        terminal = str(final.get("status") or ("timeout" if poll.get("timed_out") else "unknown"))
        if terminal not in {"completed", "success", "done"}:
            return {
                "status": "failed",
                "canonical_status": "failed",
                "shadow_status": "not_run",
                "reason": f"prediction_job_{terminal}",
                "prediction_job_id": job_id,
                "cohort_type": "true_forward",
            }

        if prod_conn is None:
            try:
                prod.close()
            except Exception:
                pass
            prod = connect(settings.sqlite_path)

        try:
            snap_id = None
            snap2 = get_snapshot(prod, fid) or {}
            if snap2.get("snapshot_id") is not None:
                snap_id = int(snap2["snapshot_id"])
            elif snap2.get("id") is not None:
                snap_id = int(snap2["id"])
            tier = fixture_tier(comp) or row.get("validation_tier") or "B"
            bridge = maybe_capture_after_prediction_persistence(
                fid,
                prod_conn=prod,
                bridge_context=ForwardEvalBridgeContext(
                    prediction_scope=scope,
                    validation_tier=str(tier),
                    public_visible=False,
                    source_job_id=job_id,
                    bridge_origin="phase6_hv_tf",
                    worldcup_stored_prediction_id=fid,
                    ecse_snapshot_id=snap_id,
                ),
                quality_status="OK",
                ecse_snapshot_id=snap_id,
            )
            freeze_meta = bridge.to_metadata_block() if hasattr(bridge, "to_metadata_block") else (bridge or {})
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "canonical_status": "freeze_failed",
                "shadow_status": "not_run",
                "reason": f"freeze_error:{type(exc).__name__}",
                "prediction_job_id": job_id,
                "cohort_type": "true_forward",
            }

        if not freeze_meta.get("freeze_id") and not freeze_meta.get("prediction_id"):
            fr2 = _load_freeze(eval_db, fid)
            if fr2:
                freeze_meta = {
                    "freeze_id": fr2.get("prediction_id"),
                    "prediction_id": fr2.get("prediction_id"),
                    "content_hash": fr2.get("content_hash"),
                    "frozen_at": fr2.get("frozen_at"),
                    "prediction_scope": fr2.get("prediction_scope") or scope,
                    "capture_status": "created",
                    "created": True,
                    "kickoff_utc": fr2.get("kickoff") or ko,
                    "lambda_home": fr2.get("lambda_home"),
                    "lambda_away": fr2.get("lambda_away"),
                }
        hash_before = freeze_meta.get("content_hash")

    if not freeze_meta.get("freeze_id") and not freeze_meta.get("prediction_id"):
        return {
            "status": "failed",
            "canonical_status": "freeze_missing",
            "shadow_status": "not_run",
            "reason": "missing_immutable_freeze",
            "cohort_type": "true_forward",
        }

    # Integrity: freeze before kickoff
    fr_dt = _parse_dt(freeze_meta.get("frozen_at"))
    if ko_dt and fr_dt and fr_dt >= ko_dt:
        return {
            "status": "blocked",
            "canonical_status": "blocked",
            "shadow_status": "not_run",
            "reason": "frozen_at_not_before_kickoff",
            "freeze_id": freeze_meta.get("freeze_id") or freeze_meta.get("prediction_id"),
            "cohort_type": "true_forward",
        }

    shadow = _run_shadow(
        prod_conn=prod,
        fixture_id=fid,
        freeze_meta=freeze_meta,
        prediction_scope=scope,
        settings=settings,
    )

    # Confirm freeze hash unchanged
    fr_after = _load_freeze(eval_db, fid) or {}
    hash_after = fr_after.get("content_hash")
    freeze_mutated = bool(hash_before and hash_after and hash_before != hash_after)

    sh_status = str(shadow.get("status") or "unknown")
    if sh_status == "success" or shadow.get("reason") == "already_success_idempotent":
        shadow_status = "success" if sh_status == "success" else "already_success_idempotent"
    elif sh_status in {"skipped", "blocked"}:
        shadow_status = sh_status
    else:
        shadow_status = "failed" if sh_status == "failed" else sh_status

    return {
        "status": "ok",
        "mode": mode,
        "canonical_status": "reused_freeze" if mode == "REUSE_IMMUTABLE_FREEZE" else "success",
        "freeze_id": freeze_meta.get("freeze_id") or freeze_meta.get("prediction_id"),
        "freeze_hash": hash_before or freeze_meta.get("content_hash"),
        "freeze_hash_after_shadow": hash_after,
        "freeze_mutated_after_shadow": freeze_mutated,
        "shadow_status": shadow_status,
        "shadow_job_id": shadow.get("job_id"),
        "shadow_reason": shadow.get("reason"),
        "cohort_type": shadow.get("cohort_type") or "true_forward",
        "canonical_unaffected": True,
        "prediction_scope": scope,
        "home_team": home,
        "away_team": away,
        "kickoff_utc": ko,
        "no_promotion": True,
    }
