"""Capture EARLY/MID/LATE research snapshots without mutating canonical freezes."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.config import GptActionsConfig, load_gpt_actions_config
from worldcup_predictor.gpt_actions.delegation import _fixture_from_db
from worldcup_predictor.gpt_actions.job_status import build_job_status_fields
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.worker import enqueue_prediction_job
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.ecse_timing_experiment.compare import compare_snapshots
from worldcup_predictor.research.ecse_timing_experiment.constants import (
    ARTIFACT_ROOT,
    PREMATCH,
    SNAPSHOT_CLASSES,
    STARTED,
    TZ_NAME,
)
from worldcup_predictor.research.ecse_timing_experiment.db import connect_timing_db
from worldcup_predictor.research.ecse_timing_experiment.discovery import discover_owner_day
from worldcup_predictor.research.ecse_timing_experiment.extract import (
    extract_model_payload,
    freeze_payload_from_eval,
    odds_blob,
)
from worldcup_predictor.research.ecse_timing_experiment.hashing import content_hash
from worldcup_predictor.research.ecse_timing_experiment.stable_union import build_stable_union
from worldcup_predictor.research.ecse_timing_experiment.state_restore import (
    backup_prediction_state,
    restore_prediction_state,
    verify_wsp_restore,
)
from worldcup_predictor.research.ecse_timing_experiment.store import (
    ensure_experiment,
    get_snapshot,
    insert_snapshot_immutable,
    list_successful_snapshots,
    upsert_comparison,
    upsert_fixture,
    upsert_stable_union,
)
from worldcup_predictor.research.ecse_timing_experiment.windows import to_vienna, window_meta

FRESH_OK = frozenset({FreshnessStatus.FRESH_ODDS.value, "fresh", "ODDS_FRESH", "FRESH_ODDS"})


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(project_root()), text=True
        ).strip()
    except Exception:
        return "unknown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _fresh_ok(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, dict):
        for key in ("freshness_flag", "odds_freshness_status", "policy_status", "freshness_class", "freshness_status"):
            if _fresh_ok(v.get(key)):
                return True
        return False
    t = str(v).strip()
    return t in FRESH_OK or ("fresh" in t.lower() and "stale" not in t.lower())


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _poll(job_id: str, store: JobStore, cfg: GptActionsConfig, deadline_s: int = 480) -> dict[str, Any]:
    deadline = time.time() + deadline_s
    final = None
    while time.time() < deadline:
        rec = store.get(job_id)
        if not rec:
            time.sleep(2)
            continue
        if "job_id" not in rec:
            rec = {**rec, "job_id": job_id}
        fields = build_job_status_fields(rec, poll_after_seconds=cfg.poll_after_seconds)
        if fields.get("terminal"):
            final = {**rec, **fields}
            break
        time.sleep(max(1, int(fields.get("poll_after_seconds") or 3)))
    return {"final": final, "timed_out": final is None}


def _load_freeze(eval_conn, fid: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        "SELECT * FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
        (int(fid),),
    ).fetchone()
    if not row:
        return None
    fr = dict(row)
    ranks = [
        dict(r)
        for r in eval_conn.execute(
            "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
            (fr["prediction_id"],),
        ).fetchall()
    ]
    fr["ranks"] = ranks
    return fr


def _freeze_hash(fr: dict[str, Any] | None) -> str | None:
    if not fr:
        return None
    return str(fr.get("content_hash") or fr.get("payload_hash") or fr.get("prediction_id") or "")


def run_timing_capture(
    *,
    experiment_date: str,
    snapshot_class: str,
    scope: str = "owner",
    dry_run: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Discover fixtures and capture one immutable snapshot class."""
    sc = snapshot_class.upper().strip()
    if sc not in SNAPSHOT_CLASSES:
        raise ValueError(f"snapshot_class must be one of {SNAPSHOT_CLASSES}")

    root = root or project_root()
    art = root / ARTIFACT_ROOT / experiment_date / sc.lower()
    art.mkdir(parents=True, exist_ok=True)
    audit_id = f"timing_{experiment_date}_{sc}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    bootstrap_gpt_actions_runtime()
    settings = get_settings()
    model = mcp_runtime.model_status()
    if not model.get("canonical_pipeline_ready") and not dry_run:
        return {
            "final_status": "ECSE_TIMING_EXPERIMENT_BLOCKED",
            "reason": "canonical_pipeline_not_ready",
            "audit_id": audit_id,
        }

    timing = connect_timing_db(root)
    experiment_id = ensure_experiment(
        timing,
        experiment_date=experiment_date,
        scope=scope,
        timezone=TZ_NAME,
        git_sha=_git_sha(),
        meta={"phase": "ECSE_TIMING_EXPERIMENT_V1", "research_only": True},
    )

    prod = connect(settings.sqlite_path)
    discovery = discover_owner_day(target_date=experiment_date, timezone=TZ_NAME, prod_conn=prod)
    _write_json(art / "discovery.json", discovery)

    for fx in discovery["included"] + discovery["excluded"]:
        upsert_fixture(timing, experiment_id=experiment_id, fixture=fx)

    if dry_run:
        return {
            "final_status": "ECSE_TIMING_EXPERIMENT_PARTIAL",
            "dry_run": True,
            "experiment_id": experiment_id,
            "discovery": {
                "included_count": discovery["included_count"],
                "excluded_count": discovery["excluded_count"],
            },
            "note": "Dry-run only — no predictions executed, freeze_capture=false",
            "audit_id": audit_id,
        }

    included = list(discovery["included"])
    # Also allow previously EXCLUDED-for-stale to be re-attempted at capture with forced refresh
    stale_candidates = [
        x for x in discovery["excluded"] if str(x.get("exclusion_reason") or "").startswith("BLOCKED_STALE_ODDS")
    ]
    # Prefer included; add stale for refresh attempt
    capture_list = included + stale_candidates
    fids = [int(x["fixture_id"]) for x in capture_list]

    eval_conn = connect_eval_db(root)
    freeze_before = {str(fid): _freeze_hash(_load_freeze(eval_conn, fid)) for fid in fids}

    backup = backup_prediction_state(prod, fids)
    _write_json(
        art / "prediction_state_backup_meta.json",
        {"fixture_ids": fids, "wsp": len(backup.get("wsp") or {}), "ecse": len(backup.get("ecse") or {})},
    )

    results: list[dict[str, Any]] = []
    captured = 0
    blocked = 0
    idempotent = 0
    restore_ok = True
    restore_meta: dict[str, Any] = {}
    capture_error: str | None = None

    try:
        for meta in capture_list:
            fid = int(meta["fixture_id"])
            existing = get_snapshot(timing, experiment_id=experiment_id, fixture_id=fid, snapshot_class=sc)
            if existing and existing.get("status") == "CAPTURED":
                idempotent += 1
                results.append(
                    {
                        **meta,
                        "status": "IDEMPOTENT_ALREADY_CAPTURED",
                        "snapshot_id": existing["snapshot_id"],
                        "research_output_hash": existing.get("research_output_hash"),
                    }
                )
                continue

            wmeta = window_meta(sc, meta.get("kickoff_utc"))
            status_now = str(meta.get("status") or "NS").upper()
            # refresh live status from DB
            row = prod.execute(
                "SELECT status, kickoff_utc FROM fixtures WHERE fixture_id=? LIMIT 1", (fid,)
            ).fetchone()
            if row:
                status_now = str(row["status"] or status_now).upper()
                if row["kickoff_utc"]:
                    meta["kickoff_utc"] = row["kickoff_utc"]
                    meta["kickoff_vienna"] = to_vienna(row["kickoff_utc"])
                    wmeta = window_meta(sc, meta["kickoff_utc"])

            if status_now in STARTED or status_now not in PREMATCH:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_FIXTURE_STARTED",
                    payload={"fixture_id": fid, "status": status_now, "research_only": True},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="BLOCKED_FIXTURE_STARTED",
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                results.append({**meta, **ins, **wmeta})
                continue

            daily = _fixture_from_db(prod, fid) or DailyFixture(
                fixture_id=fid,
                provider_fixture_id=fid,
                competition_key=str(meta.get("competition_key") or ""),
                home_team=str(meta.get("home_team") or ""),
                away_team=str(meta.get("away_team") or ""),
                kickoff_utc=str(meta.get("kickoff_utc") or ""),
                status=status_now,
                season=None,
            )
            forced = refresh_live_odds(daily, settings=settings)
            prod.close()
            prod = connect(settings.sqlite_path)
            gate = ensure_fresh_odds_before_prediction(
                prod,
                {"fixture_id": fid, "kickoff_utc": meta.get("kickoff_utc"), "status": status_now},
                daily,
                settings=settings,
                refresh_if_needed=True,
            )
            after = odds_blob(get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=meta.get("kickoff_utc")))
            complete = all(
                after.get(k) is not None and float(after.get(k) or 0) > 1 for k in ("home", "draw", "away")
            )
            fresh = bool(gate.get("allowed")) and complete and _fresh_ok(
                after.get("freshness_status") or (gate.get("freshness") or {})
            )
            if not complete:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_INCOMPLETE_ODDS",
                    payload={"odds": after, "gate": gate, "refresh": forced, "research_only": True},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="BLOCKED_INCOMPLETE_ODDS",
                    odds_content_hash=after.get("content_hash"),
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                results.append({**meta, **ins, **wmeta, "odds": after})
                continue
            if not fresh:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_STALE_ODDS",
                    payload={"odds": after, "gate": gate, "refresh": forced, "research_only": True},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="BLOCKED_STALE_ODDS",
                    odds_content_hash=after.get("content_hash"),
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                results.append({**meta, **ins, **wmeta, "odds": after})
                continue

            job_dir = art / f"jobs_{audit_id}"
            base_cfg = load_gpt_actions_config()
            cfg = GptActionsConfig(
                host=base_cfg.host,
                port=base_cfg.port,
                api_key=base_cfg.api_key,
                audit_log_path=str(art / "audit.jsonl"),
                job_store_dir=str(job_dir),
                max_jobs_retained=200,
                rate_limit_per_minute=base_cfg.rate_limit_per_minute,
                max_fixture_ids_per_job=base_cfg.max_fixture_ids_per_job,
                max_response_chars=base_cfg.max_response_chars,
                poll_after_seconds=base_cfg.poll_after_seconds,
            )
            store = JobStore(str(job_dir), max_retained=200)
            job_id = str(uuid.uuid4())
            record = {
                "job_id": job_id,
                "status": "queued",
                "created_at": _utc_now(),
                "request": {
                    "fixture_ids": [fid],
                    "prediction_scope": meta.get("prediction_scope") or "owner_shadow",
                    "refresh_if_stale": True,
                    "include_all_predictions": True,
                    "freeze_capture": False,
                    "research_only": True,
                    "official_freeze": False,
                    "timing_experiment": True,
                    "snapshot_class": sc,
                },
            }
            store._path(job_id).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            try:
                enqueue_prediction_job(job_id, store=store, config=cfg)
                poll = _poll(job_id, store, cfg)
                final = poll.get("final") or store.get(job_id) or {}
            except Exception as exc:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_PROVIDER_FAILURE",
                    payload={"error": str(exc), "research_only": True},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="BLOCKED_PROVIDER_FAILURE",
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                results.append({**meta, **ins, **wmeta, "error": str(exc)})
                continue

            prod.close()
            prod = connect(settings.sqlite_path)
            pred = extract_model_payload(prod, fid, after)
            if not pred.get("complete"):
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_MODEL_FAILURE",
                    payload={"prediction": pred, "job": final, "odds": after, "research_only": True},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="BLOCKED_MODEL_FAILURE",
                    odds_content_hash=after.get("content_hash"),
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                results.append({**meta, **ins, **wmeta})
                continue

            fr = _load_freeze(eval_conn, fid)
            payload = {
                **pred,
                "identity": {
                    "experiment_id": experiment_id,
                    "experiment_date": experiment_date,
                    "fixture_id": fid,
                    "home_team": meta.get("home_team"),
                    "away_team": meta.get("away_team"),
                    "league": meta.get("league"),
                    "country": meta.get("country"),
                    "kickoff_utc": meta.get("kickoff_utc"),
                    "kickoff_vienna": meta.get("kickoff_vienna"),
                    "snapshot_class": sc,
                    "hours_to_kickoff": wmeta["hours_to_kickoff"],
                    "window_classification": wmeta["window_classification"],
                },
                "integrity": {
                    "earliest_canonical_freeze_id": (fr or {}).get("prediction_id"),
                    "earliest_canonical_freeze_hash": _freeze_hash(fr),
                    "freeze_capture": False,
                    "temporary_run_audit_id": audit_id,
                    "job_id": job_id,
                    "job_status": final.get("status"),
                },
                "model_config_hash": content_hash(
                    {"model_version": pred.get("model_version"), "snapshot_class": sc, "phase": "V1"}
                ),
            }
            ins = insert_snapshot_immutable(
                timing,
                experiment_id=experiment_id,
                fixture_id=fid,
                snapshot_class=sc,
                status="CAPTURED",
                payload=payload,
                window_classification=wmeta["window_classification"],
                hours_to_kickoff=wmeta["hours_to_kickoff"],
                captured_at_utc=_utc_now(),
                captured_at_vienna=to_vienna(_utc_now()),
                odds_content_hash=after.get("content_hash"),
                model_config_hash=payload["model_config_hash"],
                freeze_id=(fr or {}).get("prediction_id"),
                freeze_hash=_freeze_hash(fr),
                freeze_unchanged=True,  # verified after restore batch
                freeze_capture=False,
                temporary_run_audit_id=audit_id,
            )
            captured += 1
            results.append({**meta, **ins, **wmeta, "prediction": payload, "odds": after})

            # Comparisons vs prior classes
            for prior in SNAPSHOT_CLASSES:
                if prior == sc:
                    break
                prior_snap = get_snapshot(timing, experiment_id=experiment_id, fixture_id=fid, snapshot_class=prior)
                if prior_snap and prior_snap.get("status") == "CAPTURED":
                    cmp = compare_snapshots(
                        prior_snap.get("payload") or {},
                        payload,
                        from_class=prior,
                        to_class=sc,
                    )
                    upsert_comparison(
                        timing, experiment_id=experiment_id, fixture_id=fid, comparison=cmp
                    )

            # Stable union if >=1 snapshots
            snaps = {}
            for cls in SNAPSHOT_CLASSES:
                s = get_snapshot(timing, experiment_id=experiment_id, fixture_id=fid, snapshot_class=cls)
                if s and s.get("status") == "CAPTURED":
                    snaps[cls] = s.get("payload") or {}
            if len(snaps) >= 1:
                union = build_stable_union(snaps)
                upsert_stable_union(
                    timing, experiment_id=experiment_id, fixture_id=fid, union_payload=union
                )
    except Exception as exc:
        capture_error = str(exc)
    finally:
        # Always restore WSP/ECSE
        try:
            prod.close()
        except Exception:
            pass
        prod = connect(settings.sqlite_path)
        restore_meta = restore_prediction_state(prod, backup)
        restore_ok = verify_wsp_restore(prod, backup, fids)

        freeze_after = {str(fid): _freeze_hash(_load_freeze(eval_conn, fid)) for fid in fids}
        freeze_unchanged = freeze_before == freeze_after

        integrity = {
            "freeze_capture": False,
            "freeze_before": freeze_before,
            "freeze_after": freeze_after,
            "freeze_unchanged": freeze_unchanged,
            "wsp_restore_ok": restore_ok,
            "restore_meta": restore_meta,
            "temporary_run_audit_id": audit_id,
            "research_only": True,
            "capture_error": capture_error,
        }
        _write_json(art / "integrity.json", integrity)
        _write_json(art / "capture_results.json", {"results": results})
        try:
            prod.close()
            eval_conn.close()
            timing.close()
        except Exception:
            pass

    if not restore_ok or capture_error:
        final_status = "ECSE_TIMING_EXPERIMENT_VALIDATION_FAILED"
    elif captured == 0 and idempotent == 0:
        final_status = "ECSE_TIMING_EXPERIMENT_BLOCKED"
    elif blocked and captured:
        final_status = "ECSE_TIMING_EXPERIMENT_PARTIAL"
    elif captured or idempotent:
        final_status = "ECSE_TIMING_EXPERIMENT_EARLY_CAPTURED" if sc == "EARLY" else "ECSE_TIMING_EXPERIMENT_PARTIAL"
    else:
        final_status = "ECSE_TIMING_EXPERIMENT_BLOCKED"

    summary = {
        "final_status": final_status,
        "experiment_id": experiment_id,
        "experiment_date": experiment_date,
        "snapshot_class": sc,
        "scope": scope,
        "audit_id": audit_id,
        "git_sha": _git_sha(),
        "captured": captured,
        "blocked": blocked,
        "idempotent": idempotent,
        "included_discovery": discovery["included_count"],
        "excluded_discovery": discovery["excluded_count"],
        "integrity": integrity,
        "mid_command": (
            f"python scripts/run_ecse_timing_experiment.py --date {experiment_date} "
            f"--snapshot mid --scope {scope}"
        ),
        "late_command": (
            f"python scripts/run_ecse_timing_experiment.py --date {experiment_date} "
            f"--snapshot late --scope {scope}"
        ),
        "evaluate_command": f"python scripts/evaluate_ecse_timing_experiment.py --date {experiment_date}",
    }
    _write_json(art / "run_summary.json", summary)
    return summary


def load_experiment_snapshots(experiment_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    conn = connect_timing_db(root)
    try:
        return list_successful_snapshots(conn, experiment_id)
    finally:
        conn.close()
