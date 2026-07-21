"""Orchestrator for forward aligned fixture scan."""

from __future__ import annotations

import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.research.canonical_ephemeral.constants import EXECUTION_MODE
from worldcup_predictor.research.ecse_timing_experiment.isolation import (
    run_isolation_preflight,
    snapshot_canonical_state,
)
from worldcup_predictor.research.forward_aligned_scan.compare import compare_scans
from worldcup_predictor.research.forward_aligned_scan.constants import (
    ARTIFACT_ROOT,
    DEFAULT_DAYS,
    REPORT_ROOT,
    STATUS_BLOCKED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_NO_FULL,
    STATUS_PARTIAL,
    STUDY_VERSION,
    TZ_NAME,
)
from worldcup_predictor.research.forward_aligned_scan.discovery import discover_range
from worldcup_predictor.research.forward_aligned_scan.predict import (
    _scan_id,
    predict_fixture,
    select_outputs,
)
from worldcup_predictor.research.forward_aligned_scan.store import persist_scan


STATUS_ISOLATION_BLOCKED = "BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN"
STATUS_FRESH_COMPLETE = "FORWARD_ALIGNED_FRESH_RESCAN_COMPLETE"
STATUS_FRESH_PARTIAL = "FORWARD_ALIGNED_FRESH_RESCAN_PARTIAL"
STATUS_FRESH_NO_STRONG = "FORWARD_ALIGNED_FRESH_RESCAN_NO_STRONG_SELECTIONS"
STATUS_FRESH_BLOCKED = "FORWARD_ALIGNED_FRESH_RESCAN_BLOCKED"
STATUS_FRESH_VALIDATION_FAILED = "FORWARD_ALIGNED_FRESH_RESCAN_VALIDATION_FAILED"


def _git_sha(ref: str = "HEAD") -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", ref], cwd=str(project_root()), text=True).strip()
    except Exception:
        return "unknown"


def _parse_fixture_ids(raw: str | list[int] | None) -> list[int] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [int(x) for x in raw]
    parts = [p.strip() for p in str(raw).replace(";", ",").split(",") if p.strip()]
    return [int(p) for p in parts]


def _ensure_log_dirs(root: Path) -> None:
    for rel in (
        ARTIFACT_ROOT,
        REPORT_ROOT,
        Path("artifacts") / "research" / "forward_aligned_fixture_scan" / "logs",
        Path("logs") / "research",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)


def run_forward_aligned_scan(
    *,
    from_date: str | None = None,
    days: int = DEFAULT_DAYS,
    scope: str = "owner",
    dry_run: bool = False,
    root: Path | None = None,
    max_fixtures: int | None = None,
    fixture_ids: str | list[int] | None = None,
    compare_to_scan: str | None = None,
    skip_isolation_preflight: bool = False,
) -> dict[str, Any]:
    root = root or project_root()
    _ensure_log_dirs(root)
    bootstrap_gpt_actions_runtime()
    settings = get_settings()

    discovery = discover_range(from_date=from_date, days=days, scope=scope)
    rng = discovery["range"]
    scan_id = _scan_id(rng["from_date"], int(rng["days"]))

    included = list(discovery.get("included") or [])
    requested_ids = _parse_fixture_ids(fixture_ids)
    fixture_id_filter_meta: dict[str, Any] = {"enabled": False}
    if requested_ids is not None:
        fixture_id_filter_meta["enabled"] = True
        fixture_id_filter_meta["requested"] = requested_ids
        window_ids = {int(r["fixture_id"]) for r in included}
        outside = [i for i in requested_ids if i not in window_ids]
        fixture_id_filter_meta["outside_window"] = outside
        if outside:
            return {
                "status": STATUS_FRESH_BLOCKED,
                "scan_id": scan_id,
                "reason": "fixture_ids_outside_requested_window",
                "fixture_id_filter": fixture_id_filter_meta,
                "discovery": discovery,
                "research_only": True,
                "official_freeze_created": False,
                "zero_write_integrity": _aggregate_zero([]),
            }
        included = [r for r in included if int(r["fixture_id"]) in set(requested_ids)]
        fixture_id_filter_meta["matched"] = [int(r["fixture_id"]) for r in included]
        missing_in_window = [i for i in requested_ids if i not in set(fixture_id_filter_meta["matched"])]
        fixture_id_filter_meta["requested_but_not_in_included"] = missing_in_window

    if max_fixtures is not None:
        included = included[: int(max_fixtures)]

    probe_ids = [int(r["fixture_id"]) for r in included[:20]] or [1494611]
    preflight: dict[str, Any] | None = None
    pre_state = snapshot_canonical_state(probe_ids)
    if not skip_isolation_preflight and not dry_run:
        preflight = run_isolation_preflight(
            experiment_id=scan_id,
            experiment_date=str(rng.get("from_date") or ""),
            snapshot_class="FORWARD_SCAN",
            fixture_ids=probe_ids,
            audit_id=f"{scan_id}_preflight",
        )
        if not preflight.get("ok"):
            return {
                "status": STATUS_ISOLATION_BLOCKED,
                "fresh_status": STATUS_FRESH_BLOCKED,
                "scan_id": scan_id,
                "study_version": STUDY_VERSION,
                "isolation_preflight": preflight,
                "canonical_state_before": pre_state,
                "discovery": discovery,
                "research_only": True,
                "official_freeze_created": False,
                "zero_write_integrity": {
                    "canonical_writes_attempted": 0,
                    "canonical_writes_completed": 0,
                    "freeze_created": False,
                    "freeze_updated": False,
                    "wsp_written": False,
                    "ecse_canonical_written": False,
                    "ok": True,
                    "proof_text": "preflight_blocked_no_scan_writes",
                },
            }

    if not included and discovery.get("raw_discovered", 0) == 0 and not requested_ids:
        payload = {
            "status": STATUS_BLOCKED,
            "fresh_status": STATUS_FRESH_BLOCKED,
            "scan_id": scan_id,
            "study_version": STUDY_VERSION,
            "discovery": discovery,
            "fixtures": [],
            "selection": select_outputs([]),
            "predicted_count": 0,
            "zero_write_integrity": _aggregate_zero([]),
            "timing_summary": {},
            "shas": {"local_head": _git_sha()},
            "dry_run": dry_run,
            "isolation_preflight": preflight,
            "canonical_state_before": pre_state,
        }
        if not dry_run:
            payload["outputs"] = persist_scan(payload, root=root)
        return payload

    prod = connect(settings.sqlite_path)
    fixtures: list[dict[str, Any]] = []
    try:
        for fx in included:
            row = predict_fixture(
                fx,
                scan_id=scan_id,
                scope=scope,
                prod_conn=prod,
                settings=settings,
                dry_run=dry_run,
            )
            fixtures.append(row)
    finally:
        try:
            prod.close()
        except Exception:
            pass

    selection = select_outputs(fixtures)
    zw = _aggregate_zero(fixtures)
    timing_summary = dict(Counter(str(r.get("timing_class") or "UNKNOWN") for r in fixtures))

    predicted = sum(1 for r in fixtures if str(r.get("prediction_status") or "").startswith("PREDICTED"))
    probs_ok = all(
        r.get("probabilities_persisted")
        for r in fixtures
        if str(r.get("prediction_status") or "").startswith("PREDICTED")
    )
    if dry_run:
        status = STATUS_PARTIAL
        fresh_status = STATUS_FRESH_PARTIAL
    elif zw.get("canonical_writes_completed", 0) > 0 or zw.get("freeze_created") or zw.get("wsp_written"):
        status = STATUS_FAILED
        fresh_status = STATUS_FRESH_VALIDATION_FAILED
    elif predicted == 0 and included:
        status = STATUS_BLOCKED
        fresh_status = STATUS_FRESH_BLOCKED
    elif not probs_ok and predicted > 0:
        status = STATUS_PARTIAL
        fresh_status = STATUS_FRESH_PARTIAL
    elif (selection.get("counts") or {}).get("tier_s_selected", 0) == 0 and (
        selection.get("counts") or {}
    ).get("tier_a_selected", 0) == 0:
        status = STATUS_NO_FULL
        fresh_status = STATUS_FRESH_NO_STRONG
    elif (selection.get("counts") or {}).get("tier_s_selected", 0) == 0:
        status = STATUS_NO_FULL
        fresh_status = STATUS_FRESH_COMPLETE
    elif predicted < len(included):
        status = STATUS_PARTIAL
        fresh_status = STATUS_FRESH_PARTIAL
    else:
        status = STATUS_COMPLETE
        fresh_status = STATUS_FRESH_COMPLETE

    vienna_now = datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y-%m-%d %H:%M:%S %Z")
    post_state = snapshot_canonical_state(probe_ids)
    state_equal = (
        pre_state.get("wsp_count") == post_state.get("wsp_count")
        and pre_state.get("ecse_count") == post_state.get("ecse_count")
        and pre_state.get("freeze_count") == post_state.get("freeze_count")
        and pre_state.get("freeze_hashes") == post_state.get("freeze_hashes")
    )

    payload: dict[str, Any] = {
        "status": status,
        "fresh_status": fresh_status,
        "scan_id": scan_id,
        "study_version": STUDY_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_vienna": vienna_now,
        "research_only": True,
        "official_freeze_created": False,
        "discovery": discovery,
        "fixture_id_filter": fixture_id_filter_meta,
        "fixtures": fixtures,
        "selection": selection,
        "predicted_count": predicted,
        "probabilities_persisted_all_predicted": probs_ok,
        "zero_write_integrity": zw,
        "timing_summary": timing_summary,
        "isolation_preflight": preflight,
        "canonical_state_before": pre_state,
        "canonical_state_after": post_state,
        "canonical_state_unchanged": state_equal,
        "shas": {
            "local_head": _git_sha("HEAD"),
            "origin_main": _git_sha("origin/main"),
        },
        "dry_run": dry_run,
        "baseline_scan_id": compare_to_scan,
        "limitations": [
            "Agreement filter remains preliminary (forensic n=71); not auto-promoted.",
            "Ephemeral predictions have no final decision authority.",
            "Very-early odds may be incomplete or immature.",
            "Official freezes require separate owner-approved command.",
            "Local HEAD may diverge from origin/main; research scan uses local ephemeral facade fixes.",
        ],
        "next_commands": {
            "validate": f"python scripts/validate_forward_aligned_fixture_scan.py --scan-id {scan_id}",
            "report": f"python scripts/report_forward_aligned_fixture_scan.py --scan-id {scan_id}",
            "evaluate": f"python scripts/evaluate_forward_aligned_fixture_scan.py --scan-id {scan_id}",
            "freeze_owner_approved": (
                f"python scripts/freeze_selected_aligned_fixtures.py --scan-id {scan_id} "
                f"--tier S --owner-approved"
            ),
        },
    }

    if compare_to_scan and not dry_run:
        try:
            payload["baseline_comparison"] = compare_scans(
                baseline_scan_id=compare_to_scan,
                fresh_payload=payload,
                root=root,
            )
        except Exception as exc:
            payload["baseline_comparison_error"] = f"{type(exc).__name__}:{exc}"

    if not dry_run:
        payload["outputs"] = persist_scan(payload, root=root)
    else:
        # Still prove dry-run ephemeral fields when isolation preflight ran
        dry_proof = {}
        if preflight:
            dry_proof = {
                "execution_mode": preflight.get("dry_run_execution_mode") or EXECUTION_MODE,
                "canonical_writes_attempted": 0,
                "canonical_writes_completed": 0,
                "freeze_created": False,
                "freeze_updated": False,
                "wsp_written": False,
                "ecse_canonical_written": False,
            }
        payload["dry_run_zero_write_proof"] = dry_proof
        payload["outputs"] = {"skipped": True}
    return payload


def _aggregate_zero(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = sum(int((r.get("zero_write") or {}).get("canonical_writes_attempted") or 0) for r in fixtures)
    completed = sum(int((r.get("zero_write") or {}).get("canonical_writes_completed") or 0) for r in fixtures)
    freeze_c = any((r.get("zero_write") or {}).get("freeze_created") for r in fixtures)
    freeze_u = any((r.get("zero_write") or {}).get("freeze_updated") for r in fixtures)
    wsp = any((r.get("zero_write") or {}).get("wsp_written") for r in fixtures)
    ecse = any((r.get("zero_write") or {}).get("ecse_canonical_written") for r in fixtures)
    return {
        "canonical_writes_attempted": attempted,
        "canonical_writes_completed": completed,
        "freeze_created": bool(freeze_c),
        "freeze_updated": bool(freeze_u),
        "wsp_written": bool(wsp),
        "ecse_canonical_written": bool(ecse),
        "proof_text": (
            f"canonical_writes_attempted={attempted}\n"
            f"canonical_writes_completed={completed}\n"
            f"freeze_created={bool(freeze_c)}\n"
            f"freeze_updated={bool(freeze_u)}\n"
            f"wsp_written={bool(wsp)}\n"
            f"ecse_canonical_written={bool(ecse)}"
        ),
        "ok": completed == 0 and not freeze_c and not freeze_u and not wsp and not ecse,
    }
