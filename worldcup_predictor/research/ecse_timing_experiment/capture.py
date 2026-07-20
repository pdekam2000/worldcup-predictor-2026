"""Capture EARLY/MID/LATE research snapshots via CANONICAL_RESEARCH_EPHEMERAL."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.delegation import _fixture_from_db
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.mcp_server import runtime as mcp_runtime
from worldcup_predictor.odds.canonical_snapshot import get_latest_valid_1x2_odds_snapshot
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, refresh_live_odds
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.research.canonical_ephemeral.constants import EXECUTION_MODE
from worldcup_predictor.research.canonical_ephemeral.facade import (
    ephemeral_prediction_to_timing_payload,
    run_ephemeral_canonical_prediction,
)
from worldcup_predictor.research.canonical_ephemeral.types import ResearchContext
from worldcup_predictor.research.canonical_ephemeral.write_guard import EphemeralWriteBlocked
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
from worldcup_predictor.research.ecse_timing_experiment.extract import odds_blob
from worldcup_predictor.research.ecse_timing_experiment.isolation import (
    run_isolation_preflight,
    snapshot_canonical_state,
)
from worldcup_predictor.research.ecse_timing_experiment.stable_union import build_stable_union
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

# Fixtures whose earliest freezes were created by the pre-ephemeral EARLY path (2026-07-21).
EARLY_FREEZE_SIDE_EFFECT_FIXTURES: dict[int, dict[str, Any]] = {
    1556501: {
        "match": "Aarhus vs Lech Poznan",
        "label": "EARLY_FREEZE_SIDE_EFFECT_CREATED",
        "experiment_audit_id": "timing_2026-07-21_EARLY_20260720T162205Z",
    },
    1556502: {
        "match": "Fenerbahçe vs Gornik Zabrze",
        "label": "EARLY_FREEZE_SIDE_EFFECT_CREATED",
        "experiment_audit_id": "timing_2026-07-21_EARLY_20260720T162205Z",
    },
    1556503: {
        "match": "Sturm Graz vs Heart Of Midlothian",
        "label": "EARLY_FREEZE_SIDE_EFFECT_CREATED",
        "experiment_audit_id": "timing_2026-07-21_EARLY_20260720T162205Z",
    },
    1556504: {
        "match": "FC Thun vs Dinamo Zagreb",
        "label": "EARLY_FREEZE_SIDE_EFFECT_CREATED",
        "experiment_audit_id": "timing_2026-07-21_EARLY_20260720T162205Z",
    },
}


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


def annotate_early_freeze_side_effects(eval_conn, audit_id: str) -> list[dict[str, Any]]:
    """Record immutable audit annotations for freezes created by the old MCP path."""
    annotations = []
    for fid, meta in EARLY_FREEZE_SIDE_EFFECT_FIXTURES.items():
        fr = _load_freeze(eval_conn, fid)
        annotations.append(
            {
                "label": "EARLY_FREEZE_SIDE_EFFECT_CREATED",
                "fixture_id": fid,
                "match": meta["match"],
                "freeze_id": None if not fr else fr.get("prediction_id"),
                "freeze_hash": _freeze_hash(fr),
                "created_timestamp": None if not fr else fr.get("frozen_at"),
                "experiment_audit_id": meta["experiment_audit_id"],
                "current_audit_id": audit_id,
                "explanation": (
                    "Freeze was created unintentionally by the pre-ephemeral MCP bridge path "
                    "during EARLY capture when freeze_capture=false was requested but not honored. "
                    "No prior freeze existed; this row is now the earliest immutable freeze."
                ),
                "must_remain_immutable": True,
                "future_mid_late_must_not_create_additional_freezes": True,
                "payload_mutated": False,
                "timestamp_mutated": False,
            }
        )
    return annotations


def run_timing_capture(
    *,
    experiment_date: str,
    snapshot_class: str,
    scope: str = "owner",
    dry_run: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Discover fixtures and capture one immutable snapshot class via ephemeral canonical execution."""
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
        meta={
            "phase": "ECSE_TIMING_EXPERIMENT_V2_EPHEMERAL",
            "research_only": True,
            "execution_mode": EXECUTION_MODE,
        },
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
            "execution_mode": EXECUTION_MODE,
            "discovery": {
                "included_count": discovery["included_count"],
                "excluded_count": discovery["excluded_count"],
            },
            "note": "Dry-run only — no predictions executed",
            "audit_id": audit_id,
        }

    included = list(discovery["included"])
    stale_candidates = [
        x for x in discovery["excluded"] if str(x.get("exclusion_reason") or "").startswith("BLOCKED_STALE_ODDS")
    ]
    capture_list = included + stale_candidates
    fids = [int(x["fixture_id"]) for x in capture_list]

    eval_conn = connect_eval_db(root)
    freeze_annotations = annotate_early_freeze_side_effects(eval_conn, audit_id)
    _write_json(art / "early_freeze_side_effect_audit.json", {"annotations": freeze_annotations})

    # MID/LATE hard isolation gate
    if sc in {"MID", "LATE"}:
        preflight = run_isolation_preflight(
            experiment_id=experiment_id,
            experiment_date=experiment_date,
            snapshot_class=sc,
            fixture_ids=fids or [int(a["fixture_id"]) for a in freeze_annotations],
            audit_id=audit_id,
        )
        _write_json(art / "isolation_preflight.json", preflight)
        if not preflight.get("ok"):
            return {
                "final_status": "ECSE_TIMING_EXPERIMENT_BLOCKED",
                "reason": "BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN",
                "preflight": preflight,
                "experiment_id": experiment_id,
                "audit_id": audit_id,
                "execution_mode": EXECUTION_MODE,
            }

    state_before = snapshot_canonical_state(fids)
    freeze_before = state_before["freeze_hashes"]

    results: list[dict[str, Any]] = []
    captured = 0
    blocked = 0
    idempotent = 0
    capture_error: str | None = None
    integrity: dict[str, Any] = {}

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
                        "execution_mode": EXECUTION_MODE,
                    }
                )
                continue

            wmeta = window_meta(sc, meta.get("kickoff_utc"))
            status_now = str(meta.get("status") or "NS").upper()
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
                    payload={"fixture_id": fid, "status": status_now, "research_only": True, "execution_mode": EXECUTION_MODE},
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
            # Odds refresh is allowed (odds tables); prediction path must remain ephemeral.
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
            odds_snap = get_latest_valid_1x2_odds_snapshot(prod, fid, kickoff_utc=meta.get("kickoff_utc"))
            after = odds_blob(odds_snap)
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
                    payload={"odds": after, "gate": gate, "refresh": forced, "research_only": True, "execution_mode": EXECUTION_MODE},
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
                    payload={"odds": after, "gate": gate, "refresh": forced, "research_only": True, "execution_mode": EXECUTION_MODE},
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

            research_ctx = ResearchContext(
                experiment_id=experiment_id,
                experiment_date=experiment_date,
                snapshot_class=sc,
                audit_id=audit_id,
                scope=scope,
                caller="ecse_timing_experiment",
            )
            try:
                eph = run_ephemeral_canonical_prediction(
                    fid,
                    scope=scope,
                    odds_snapshot=odds_snap,
                    research_context=research_ctx,
                    settings=settings,
                    prod_conn=prod,
                )
            except EphemeralWriteBlocked as exc:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_MODEL_FAILURE",
                    payload={"error": str(exc), "research_only": True, "execution_mode": EXECUTION_MODE},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="EPHEMERAL_WRITE_BLOCKED",
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                capture_error = str(exc)
                results.append({**meta, **ins, **wmeta, "error": str(exc)})
                break
            except Exception as exc:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_MODEL_FAILURE",
                    payload={"error": str(exc), "research_only": True, "execution_mode": EXECUTION_MODE},
                    window_classification=wmeta["window_classification"],
                    hours_to_kickoff=wmeta["hours_to_kickoff"],
                    captured_at_utc=_utc_now(),
                    captured_at_vienna=to_vienna(_utc_now()),
                    block_reason="BLOCKED_MODEL_FAILURE",
                    freeze_capture=False,
                    temporary_run_audit_id=audit_id,
                )
                blocked += 1
                results.append({**meta, **ins, **wmeta, "error": str(exc)})
                continue

            if not eph.complete:
                ins = insert_snapshot_immutable(
                    timing,
                    experiment_id=experiment_id,
                    fixture_id=fid,
                    snapshot_class=sc,
                    status="BLOCKED_MODEL_FAILURE",
                    payload={
                        "prediction": eph.to_dict(),
                        "odds": after,
                        "research_only": True,
                        "execution_mode": EXECUTION_MODE,
                    },
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
            side = next((a for a in freeze_annotations if a["fixture_id"] == fid), None)
            payload = ephemeral_prediction_to_timing_payload(
                eph,
                identity={
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
                    "execution_mode": EXECUTION_MODE,
                },
                integrity={
                    "earliest_canonical_freeze_id": (fr or {}).get("prediction_id"),
                    "earliest_canonical_freeze_hash": _freeze_hash(fr),
                    "freeze_capture": False,
                    "temporary_run_audit_id": audit_id,
                    "execution_mode": EXECUTION_MODE,
                    "canonical_writes_attempted": eph.canonical_writes_attempted,
                    "canonical_writes_completed": 0,
                    "freeze_created": False,
                    "freeze_updated": False,
                    "wsp_written": False,
                    "ecse_canonical_written": False,
                    "early_freeze_side_effect": side,
                },
            )
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
                model_config_hash=eph.model_config_hash,
                freeze_id=(fr or {}).get("prediction_id"),
                freeze_hash=_freeze_hash(fr),
                freeze_unchanged=True,
                freeze_capture=False,
                temporary_run_audit_id=audit_id,
            )
            captured += 1
            results.append({**meta, **ins, **wmeta, "prediction": payload, "odds": after})

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

            snaps = {}
            for cls in SNAPSHOT_CLASSES:
                s = get_snapshot(timing, experiment_id=experiment_id, fixture_id=fid, snapshot_class=cls)
                if s and s.get("status") == "CAPTURED":
                    snaps[cls] = s.get("payload") or {}
            if snaps:
                union = build_stable_union(snaps)
                upsert_stable_union(
                    timing, experiment_id=experiment_id, fixture_id=fid, union_payload=union
                )
    except Exception as exc:
        capture_error = str(exc)
    finally:
        state_after = snapshot_canonical_state(fids)
        freeze_after = state_after["freeze_hashes"]
        freeze_unchanged = freeze_before == freeze_after
        freeze_mutated = [
            int(fid)
            for fid in fids
            if freeze_before.get(str(fid))
            and freeze_after.get(str(fid))
            and freeze_before.get(str(fid)) != freeze_after.get(str(fid))
        ]
        freeze_newly_created = [
            int(fid)
            for fid in fids
            if freeze_before.get(str(fid)) is None and freeze_after.get(str(fid)) is not None
        ]
        integrity = {
            "execution_mode": EXECUTION_MODE,
            "freeze_capture": False,
            "freeze_before": freeze_before,
            "freeze_after": freeze_after,
            "freeze_unchanged": freeze_unchanged,
            "freeze_newly_created_by_bridge": freeze_newly_created,
            "freeze_hash_mutated": freeze_mutated,
            "canonical_state_before": state_before,
            "canonical_state_after": state_after,
            "wsp_count_unchanged": state_before["wsp_count"] == state_after["wsp_count"],
            "ecse_count_unchanged": state_before["ecse_count"] == state_after["ecse_count"],
            "freeze_count_unchanged": state_before["freeze_count"] == state_after["freeze_count"],
            "canonical_writes_attempted": 0,
            "canonical_writes_completed": 0,
            "early_freeze_side_effect_annotations": freeze_annotations,
            "temporary_run_audit_id": audit_id,
            "research_only": True,
            "capture_error": capture_error,
            "note": (
                "V2 ephemeral path: no GPT Actions job, no WSP/ECSE/freeze writes. "
                "Odds refresh may update odds_snapshots only."
            ),
        }
        _write_json(art / "integrity.json", integrity)
        _write_json(art / "capture_results.json", {"results": results})
        try:
            prod.close()
            eval_conn.close()
            timing.close()
        except Exception:
            pass

    isolation_ok = (
        integrity.get("freeze_unchanged")
        and integrity.get("wsp_count_unchanged")
        and integrity.get("ecse_count_unchanged")
        and integrity.get("freeze_count_unchanged")
        and not freeze_mutated
        and not freeze_newly_created
        and not capture_error
    )

    if not isolation_ok or capture_error or freeze_mutated or freeze_newly_created:
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
        "execution_mode": EXECUTION_MODE,
        "captured": captured,
        "blocked": blocked,
        "idempotent": idempotent,
        "included_discovery": discovery["included_count"],
        "excluded_discovery": discovery["excluded_count"],
        "integrity": integrity,
        "isolation_ok": isolation_ok,
        "mid_command": (
            f"python scripts/run_ecse_timing_experiment.py --date {experiment_date} "
            f"--snapshot mid --scope {scope}"
        ),
        "late_command": (
            f"python scripts/run_ecse_timing_experiment.py --date {experiment_date} "
            f"--snapshot late --scope {scope}"
        ),
        "evaluate_command": f"python scripts/evaluate_ecse_timing_experiment.py --date {experiment_date}",
        "mid_authorized": bool(isolation_ok and sc == "EARLY" and (captured or idempotent)),
    }
    _write_json(art / "run_summary.json", summary)
    return summary


def load_experiment_snapshots(experiment_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    conn = connect_timing_db(root)
    try:
        return list_successful_snapshots(conn, experiment_id)
    finally:
        conn.close()
