"""PHASE ECSE-ODDALERTS-6 — Daily owner pipeline: Gmail CSV → snapshots → shadow monitor."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
    build_ecse_readiness_summary,
    build_policy_market_matrix,
    preview_odds_snapshot_payloads,
)
from worldcup_predictor.data_import.oddalerts_csv_incremental_importer import (
    IMPORT_SUMMARY_PATH,
    INBOX_DIR,
    import_inbox_incremental,
)
from worldcup_predictor.data_import.oddalerts_csv_promotion_dryrun import (
    SOURCE_PROVIDER,
    artifact_paths as dryrun_artifact_paths,
    run_promotion_dryrun,
)
from worldcup_predictor.data_import.oddalerts_csv_promotion_write import (
    create_pre_write_backup,
    filter_write_candidates,
    run_promotion_write,
    write_artifact_paths as promotion_write_paths,
)
from worldcup_predictor.research.oddalerts_ecse_monitor import (
    ELIGIBLE_V2,
    artifact_paths as monitor_artifact_paths,
    discover_monitor_candidates,
    ensure_monitor_table,
    evaluate_monitor_records,
    generate_monitor_prediction,
    monitor_run_id,
    write_monitor_records,
)
from worldcup_predictor.research.oddalerts_ecse_segment_calibration import _batch_wde
from worldcup_predictor.research.oddalerts_ecse_segments import SEGMENT_MODEL_V2, load_v2_calibration_context

logger = logging.getLogger(__name__)

PHASE = "ECSE-ODDALERTS-6"
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
REPORT_PATH = Path("DAILY_ODDALERTS_ECSE_OWNER_PIPELINE_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def resolve_process_date(date_arg: str) -> str:
    if date_arg.lower() == "today":
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return date_arg


def window_end(date_from: str, window_days: int) -> str:
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = start + timedelta(days=max(1, window_days) - 1)
    return end.strftime("%Y-%m-%d")


def state_artifact_path(process_date: str) -> Path:
    tag = process_date.replace("-", "")
    return Path(f"artifacts/daily_oddalerts_ecse_owner_pipeline_state_{tag}.json")


def owner_report_json_path(process_date: str) -> Path:
    tag = process_date.replace("-", "")
    return Path(f"artifacts/daily_oddalerts_ecse_owner_{tag}.json")


def owner_report_md_path(process_date: str) -> Path:
    tag = process_date.replace("-", "")
    return Path(f"reports/owner/daily_oddalerts_ecse_owner_{tag}.md")


def _artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _date_tag(process_date: str) -> str:
    return process_date.replace("-", "")


def policy_artifact_paths(process_date: str) -> dict[str, Path]:
    tag = _date_tag(process_date)
    return {
        "matrix": Path(f"artifacts/oddalerts_policy_market_matrix_{tag}.json"),
        "ecse_readiness": Path(f"artifacts/oddalerts_policy_ecse_readiness_{tag}.json"),
        "policy_preview": Path(f"artifacts/oddalerts_policy_odds_snapshot_preview_{tag}.json"),
        "dryrun": dryrun_artifact_paths(process_date)["dryrun_out"],
        "bookmaker_validation": Path(f"artifacts/oddalerts_bookmaker_policy_validation_{tag}.json"),
    }


@dataclass
class DailyPipelineConfig:
    process_date: str = "today"
    window_days: int = 7
    download_gmail: bool = False
    import_csv: bool = False
    promote_odds_safe: bool = False
    run_monitor: bool = False
    only_eligible_v2: bool = True
    pipeline_tag: str = "daily-owner-oddalerts"
    dry_run_promotion: bool = True
    verbose: bool = False


@dataclass
class DailyPipelineResult:
    run_id: str
    process_date: str
    date_from: str
    date_to: str
    window_days: int
    steps: list[dict[str, Any]] = field(default_factory=list)
    gmail: dict[str, Any] = field(default_factory=dict)
    import_summary: dict[str, Any] = field(default_factory=dict)
    ready_full_before: int = 0
    ready_full_after: int = 0
    promotion: dict[str, Any] = field(default_factory=dict)
    monitor: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    production_guard: dict[str, Any] = field(default_factory=dict)
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    final_recommendation: str = "DAILY_OWNER_PIPELINE_READY"

    def to_state_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "run_id": self.run_id,
            "generated_at_utc": _utc_now(),
            "date": self.process_date,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "window_days": self.window_days,
            "gmail_emails_scanned": self.gmail.get("emails_found", 0),
            "csv_links_found": self.gmail.get("links_found", 0),
            "files_downloaded": self.gmail.get("files_downloaded", 0),
            "duplicates_skipped": self.gmail.get("duplicates_skipped", 0),
            "rows_imported": self.import_summary.get("probability_staged", 0)
            + self.import_summary.get("enrichment_imported", 0),
            "ready_full_before": self.ready_full_before,
            "ready_full_after": self.ready_full_after,
            "odds_snapshots_inserted": self.promotion.get("inserted_count", 0),
            "odds_snapshots_enriched": self.promotion.get("enriched_count", 0),
            "odds_snapshots_skipped": self.promotion.get("skipped_count", 0),
            "monitor_candidates_discovered": self.monitor.get("discovered_count", 0),
            "monitor_records_written": self.monitor.get("written_count", 0),
            "monitor_records_skipped_non_eligible": self.monitor.get("skipped_ineligible_count", 0),
            "evaluated_records": self.evaluation.get("evaluated_count", 0),
            "validation_statuses": self.validation,
            "skipped_reasons": self.skipped_reasons,
            "production_guard": self.production_guard,
            "final_recommendation": self.final_recommendation,
            "steps": self.steps,
        }


def _run_script(
    script_name: str,
    script_args: list[str] | tuple[str, ...] = (),
    *,
    ok_exit_codes: frozenset[int] | None = None,
) -> dict[str, Any]:
    cmd = [sys.executable, str(SCRIPTS / script_name), *script_args]
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    ok_codes = ok_exit_codes or frozenset({0})
    return {
        "script": script_name,
        "args": list(script_args),
        "returncode": proc.returncode,
        "success": proc.returncode in ok_codes,
        "stdout_tail": (proc.stdout or "")[-2500:],
        "stderr_tail": (proc.stderr or "")[-1500:],
    }


def _count_table(conn, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"])


def _ready_full_count(process_date: str) -> int:
    ecse = _artifact(policy_artifact_paths(process_date)["ecse_readiness"])
    if ecse:
        return int((ecse.get("status_counts") or {}).get("READY_FULL", ecse.get("ready_full_count", 0)) or 0)
    fallback = sorted(Path("artifacts").glob("oddalerts_policy_ecse_readiness_*.json"))
    if fallback:
        fb = _artifact(fallback[-1])
        return int((fb.get("status_counts") or {}).get("READY_FULL", fb.get("ready_full_count", 0)) or 0)
    return 0


def _fixture_kickoffs(conn, fixture_ids: list[int]) -> dict[int, str]:
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" * len(fixture_ids))
    rows = conn.execute(
        f"SELECT fixture_id, kickoff_utc FROM fixtures WHERE fixture_id IN ({placeholders})",
        fixture_ids,
    ).fetchall()
    return {int(r["fixture_id"]): str(r["kickoff_utc"] or "") for r in rows}


def _has_disagreement_block(candidate: dict[str, Any]) -> bool:
    preview = candidate.get("snapshot_payload_preview") or {}
    meta = preview.get("metadata") or {}
    if meta.get("disagreement_flag"):
        return True
    warnings = meta.get("normalization_warnings") or []
    return any("disagreement" in str(w).lower() for w in warnings)


def filter_daily_safe_candidates(
    dryrun: dict[str, Any],
    conn,
    *,
    date_from: str,
    date_to: str,
    allow_enrich_placeholders: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """READY_FULL + safe action + kickoff window + no disagreement + no fresh conflict."""
    base = filter_write_candidates(dryrun, allow_enrich_placeholders=allow_enrich_placeholders)
    if not base:
        return [], []

    kickoffs = _fixture_kickoffs(conn, [int(c["fixture_id"]) for c in base])
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for cand in base:
        fid = int(cand["fixture_id"])
        kick = kickoffs.get(fid, "")
        kick_date = kick[:10] if kick else ""
        if kick_date and (kick_date < date_from or kick_date > date_to):
            rejected.append({"fixture_id": fid, "reason": "outside_kickoff_window"})
            continue
        if _has_disagreement_block(cand):
            rejected.append({"fixture_id": fid, "reason": "high_disagreement_block"})
            continue
        if cand.get("promotion_action") == "SKIP_EXISTING_FRESH":
            rejected.append({"fixture_id": fid, "reason": "fresh_provider_conflict"})
            continue
        kept.append(cand)
    return kept, rejected


def run_gmail_download(process_date: str, *, pipeline_tag: str, dry_run: bool = False) -> dict[str, Any]:
    args = ["--date", process_date, "--tag-ecse-lower-band", "--tag", pipeline_tag]
    if dry_run:
        args.append("--dry-run")
    tag_path = Path(f"artifacts/oddalerts_today_gmail_summary_{_date_tag(process_date)}.json")
    step = _run_script(
        "download_today_oddalerts_csv_from_gmail.py",
        args,
        ok_exit_codes=frozenset({0, 3}),
    )
    summary = _artifact(tag_path)
    lb_path = Path(f"artifacts/oddalerts_lower_band_gmail_summary_{_date_tag(process_date)}.json")
    lb = _artifact(lb_path)
    payload = lb or summary
    return {
        **step,
        "pipeline_tag": pipeline_tag,
        "emails_found": payload.get("emails_found", 0),
        "links_found": payload.get("links_found", payload.get("total_links", 0)),
        "files_downloaded": payload.get("files_downloaded", payload.get("total_new_files", 0)),
        "duplicates_skipped": payload.get("duplicates_skipped", payload.get("total_duplicates_skipped", 0)),
        "artifact": str(tag_path),
    }


def run_incremental_import(conn, *, input_dir: Path = INBOX_DIR, dry_run: bool = False) -> dict[str, Any]:
    batch = import_inbox_incremental(conn, input_dir=input_dir.resolve(), dry_run=dry_run)
    summary = batch.to_dict()
    if IMPORT_SUMMARY_PATH.exists():
        summary = json.loads(IMPORT_SUMMARY_PATH.read_text(encoding="utf-8"))
    return summary


def run_policy_audit_chain(conn, process_date: str, *, full_audit: bool = False) -> dict[str, Any]:
    """Market mapping + policy matrix + dryrun preview (lightweight by default)."""
    paths = policy_artifact_paths(process_date)
    results: dict[str, Any] = {"process_date": process_date, "full_audit": full_audit}

    if full_audit:
        for script, extra in (
            ("audit_oddalerts_csv_all_markets.py", ["--date", process_date]),
            ("validate_oddalerts_all_market_mapping.py", []),
        ):
            step = _run_script(script, extra, ok_exit_codes=frozenset({0, 1}))
            results[script] = step

    matrix = build_policy_market_matrix(conn, allow_high_disagreement=False)
    ecse = build_ecse_readiness_summary(matrix)
    paths["matrix"].parent.mkdir(parents=True, exist_ok=True)
    paths["matrix"].write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["ecse_readiness"].write_text(json.dumps(ecse, indent=2, ensure_ascii=False), encoding="utf-8")
    preview = preview_odds_snapshot_payloads(matrix)
    paths["policy_preview"].write_text(json.dumps(preview, indent=2, ensure_ascii=False), encoding="utf-8")
    dryrun = run_promotion_dryrun(conn, process_date=process_date)
    paths["dryrun"].parent.mkdir(parents=True, exist_ok=True)
    paths["dryrun"].write_text(json.dumps(dryrun, indent=2, ensure_ascii=False), encoding="utf-8")
    results["inline_policy_refresh"] = True

    if full_audit:
        for script, extra in (
            ("build_oddalerts_policy_market_matrix.py", []),
            ("preview_oddalerts_policy_to_odds_snapshots.py", []),
            ("validate_oddalerts_bookmaker_policy.py", []),
            ("preview_promote_oddalerts_csv_to_odds_snapshots.py", ["--date", process_date]),
        ):
            step = _run_script(script, extra, ok_exit_codes=frozenset({0, 1}))
            results[script] = step

    results["ready_full"] = _ready_full_count(process_date)
    results["bookmaker_validation"] = _artifact(paths["bookmaker_validation"])
    return results


def run_safe_odds_promotion(
    conn,
    *,
    process_date: str,
    date_from: str,
    date_to: str,
    write: bool,
) -> dict[str, Any]:
    paths = promotion_write_paths(process_date)
    dryrun_path = paths["dryrun"]
    if not dryrun_path.exists():
        dryrun_path = policy_artifact_paths(process_date)["dryrun"]
    if not dryrun_path.exists():
        return {"status": "skipped", "reason": "missing_dryrun_artifact"}

    dryrun = json.loads(dryrun_path.read_text(encoding="utf-8"))
    book_val = _artifact(policy_artifact_paths(process_date)["bookmaker_validation"])
    book_passed = True
    if isinstance(book_val.get("checks"), list) and book_val["checks"]:
        book_passed = all(c.get("passed") for c in book_val["checks"])

    safe_candidates, rejected = filter_daily_safe_candidates(
        dryrun, conn, date_from=date_from, date_to=date_to
    )
    filtered_dryrun = {**dryrun, "candidates": safe_candidates}

    odds_before = _count_table(conn, "odds_snapshots")
    ecse_before = _count_table(conn, "ecse_prediction_snapshots")
    wde_before = _count_table(conn, "worldcup_stored_predictions")

    result: dict[str, Any] = {
        "write_mode": write,
        "book_validation_passed": book_passed,
        "safe_candidate_count": len(safe_candidates),
        "rejected_count": len(rejected),
        "rejected": rejected[:50],
        "inserted_count": 0,
        "enriched_count": 0,
        "skipped_count": 0,
        "backup": None,
    }

    if not safe_candidates:
        result["status"] = "no_safe_candidates"
        return result
    if not book_passed:
        result["status"] = "validation_failed"
        return result

    backup_info = None
    if write:
        db_path = get_db_path(get_settings().sqlite_path)
        backup_info = create_pre_write_backup(db_path)
        result["backup"] = backup_info
        if not backup_info.get("backup_success"):
            result["status"] = "backup_failed"
            return result

    write_result = run_promotion_write(
        conn,
        dryrun=filtered_dryrun,
        write=write,
        allow_enrich_placeholders=True,
        no_overwrite_fresh_provider=True,
        process_date=process_date,
        backup_info=backup_info,
    )
    result.update(write_result)
    result["odds_snapshots_before"] = odds_before
    result["odds_snapshots_after"] = _count_table(conn, "odds_snapshots")
    result["ecse_snapshots_before"] = ecse_before
    result["ecse_snapshots_after"] = _count_table(conn, "ecse_prediction_snapshots")
    result["wde_before"] = wde_before
    result["wde_after"] = _count_table(conn, "worldcup_stored_predictions")
    result["status"] = "written" if write else "dry_run_preview"
    paths["write_out"].parent.mkdir(parents=True, exist_ok=True)
    paths["write_out"].write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def run_limited_shadow_monitor(
    conn,
    *,
    date_from: str,
    date_to: str,
    write_shadow: bool,
    only_eligible_v2: bool,
) -> dict[str, Any]:
    ensure_monitor_table(conn)
    run_id = monitor_run_id(date_from, date_to)
    discovery = discover_monitor_candidates(conn, date_from=date_from, date_to=date_to)
    paths = monitor_artifact_paths(date_from, date_to)
    paths["candidates"].write_text(json.dumps(discovery, indent=2, ensure_ascii=False), encoding="utf-8")

    v2_ctx = load_v2_calibration_context()
    calibration = v2_ctx.get("calibration")
    utility_percentiles = v2_ctx.get("utility_percentiles")
    candidates = discovery.get("candidates") or []
    wde_map = _batch_wde(conn, [int(c["fixture_id"]) for c in candidates])

    generated: list[dict] = []
    skipped_ineligible: list[dict] = []
    failed: list[dict] = []

    for cand in candidates:
        out = generate_monitor_prediction(
            conn,
            cand,
            calibration=calibration,
            utility_percentiles=utility_percentiles,
            wde_direction=wde_map.get(int(cand["fixture_id"])),
        )
        if out.get("status") != "generated":
            failed.append(out)
            continue
        elig = out["segment_v2"].get("promotion_eligibility_v2")
        if only_eligible_v2 and elig not in ELIGIBLE_V2:
            skipped_ineligible.append({"fixture_id": cand["fixture_id"], "eligibility": elig})
            continue
        generated.append({**out, "candidate": cand})

    write_result = write_monitor_records(
        conn,
        generated,
        monitor_run_id_val=run_id,
        dry_run=not write_shadow,
    )

    evaluation = evaluate_monitor_records(conn, monitor_run_id_val=run_id)
    paths["evaluation"].write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")

    run_out = {
        "monitor_run_id": run_id,
        "discovered_count": discovery.get("candidate_count", 0),
        "generated_count": len(generated),
        "failed_count": len(failed),
        "skipped_ineligible_count": len(skipped_ineligible),
        "written_count": write_result.get("written_count", write_result.get("would_write_count", 0)),
        "skipped_monitor_count": write_result.get("skipped_count", 0),
        "discovery_skipped": discovery.get("skipped", [])[:30],
    }
    paths["run_out"].write_text(json.dumps(run_out, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**run_out, "evaluation": evaluation, "write_result": write_result}


def pipeline_final_recommendation(result: DailyPipelineResult) -> str:
    gmail_files = result.gmail.get("files_downloaded", 0)
    imported = result.import_summary.get("probability_staged", 0) + result.import_summary.get(
        "enrichment_imported", 0
    )
    inserted = result.promotion.get("inserted_count", 0) + result.promotion.get("enriched_count", 0)
    monitor_written = result.monitor.get("written_count", 0)
    candidates = result.monitor.get("discovered_count", 0)
    promo_status = result.promotion.get("status")

    if promo_status == "backup_failed":
        return "DO_NOT_RUN_DAILY_PIPELINE"
    if promo_status == "validation_failed":
        return "NEED_ODDS_PROMOTION_REVIEW"

    if monitor_written > 0:
        return "DAILY_OWNER_PIPELINE_ACTIVE_WITH_SIGNALS"
    if candidates > 0 and monitor_written == 0:
        return "NEED_ODDS_PROMOTION_REVIEW"
    if inserted > 0 or gmail_files > 0 or imported > 0:
        return "DAILY_OWNER_PIPELINE_ACTIVE_NO_NEW_DATA"
    if result.gmail.get("emails_found", 0) == 0 and not imported:
        return "NEED_NEW_ODDALERTS_EXPORTS"
    if candidates == 0 and result.skipped_reasons.get("no_oddalerts_snapshot", 0) > 0:
        return "NEED_NEW_ODDALERTS_EXPORTS"
    return "DAILY_OWNER_PIPELINE_ACTIVE_NO_NEW_DATA"


def collect_production_guard(conn) -> dict[str, int]:
    return {
        "ecse_prediction_snapshots": _count_table(conn, "ecse_prediction_snapshots"),
        "odds_snapshots": _count_table(conn, "odds_snapshots"),
        "worldcup_stored_predictions": _count_table(conn, "worldcup_stored_predictions"),
    }


def run_daily_oddalerts_ecse_owner_pipeline(config: DailyPipelineConfig) -> DailyPipelineResult:
    process_date = resolve_process_date(config.process_date)
    date_from = process_date
    date_to = window_end(process_date, config.window_days)
    run_id = f"daily_oa_ecse_{process_date.replace('-', '')}_{uuid.uuid4().hex[:8]}"

    conn = connect(get_settings().sqlite_path)
    guard_before = collect_production_guard(conn)
    result = DailyPipelineResult(
        run_id=run_id,
        process_date=process_date,
        date_from=date_from,
        date_to=date_to,
        window_days=config.window_days,
        ready_full_before=_ready_full_count(process_date),
        production_guard={"before": guard_before},
    )

    if config.download_gmail:
        try:
            step = run_gmail_download(process_date, pipeline_tag=config.pipeline_tag)
        except Exception as exc:
            step = {"success": False, "error": str(exc), "emails_found": 0, "files_downloaded": 0}
        result.steps.append(step)
        result.gmail = step

    if config.import_csv:
        step_summary = run_incremental_import(conn, dry_run=False)
        result.steps.append({"step": "import_csv", "summary": step_summary})
        result.import_summary = step_summary

    policy_step = run_policy_audit_chain(
        conn,
        process_date,
        full_audit=config.import_csv or bool(result.gmail.get("files_downloaded")),
    )
    result.steps.append({"step": "policy_audit_chain", **policy_step})
    result.ready_full_after = _ready_full_count(process_date)

    if config.promote_odds_safe:
        write = not config.dry_run_promotion
        promo = run_safe_odds_promotion(
            conn,
            process_date=process_date,
            date_from=date_from,
            date_to=date_to,
            write=write,
        )
        result.steps.append({"step": "promote_odds_safe", **promo})
        result.promotion = promo

    if config.run_monitor:
        mon = run_limited_shadow_monitor(
            conn,
            date_from=date_from,
            date_to=date_to,
            write_shadow=True,
            only_eligible_v2=config.only_eligible_v2,
        )
        result.steps.append({"step": "limited_shadow_monitor", **mon})
        result.monitor = mon
        result.evaluation = mon.get("evaluation") or {}
        result.evaluation["evaluated_count"] = (mon.get("evaluation") or {}).get("evaluated_count", 0)
        skipped = mon.get("discovery_skipped") or []
        for s in skipped:
            reason = s.get("reason", "unknown")
            result.skipped_reasons[reason] = result.skipped_reasons.get(reason, 0) + 1

    guard_after = collect_production_guard(conn)
    result.production_guard["after"] = guard_after
    conn.close()

    result.final_recommendation = pipeline_final_recommendation(result)
    state_path = state_artifact_path(process_date)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(result.to_state_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    from worldcup_predictor.owner.daily_oddalerts_ecse_owner_report import build_daily_oddalerts_ecse_owner_report

    build_daily_oddalerts_ecse_owner_report(result)
    return result


def load_latest_pipeline_state(process_date: str | None = None) -> dict[str, Any]:
    if process_date:
        return _artifact(state_artifact_path(process_date))
    candidates = sorted(Path("artifacts").glob("daily_oddalerts_ecse_owner_pipeline_state_*.json"))
    if not candidates:
        return {}
    return _artifact(candidates[-1])


def build_owner_daily_summary(conn, *, process_date: str | None = None) -> dict[str, Any]:
    """Summary card fields for Owner Lab API."""
    state = load_latest_pipeline_state(process_date)
    ensure_monitor_table(conn)
    today_tag = (process_date or resolve_process_date("today")).replace("-", "")

    monitor_total = int(
        conn.execute("SELECT COUNT(*) c FROM ecse_oddalerts_shadow_monitor").fetchone()["c"]
    )
    upcoming = int(
        conn.execute(
            """
            SELECT COUNT(*) c FROM ecse_oddalerts_shadow_monitor
            WHERE final_score IS NULL
            """
        ).fetchone()["c"]
    )
    eligible_upcoming = conn.execute(
        """
        SELECT home_team, away_team, competition, kickoff_utc, top_1_score,
               segment_badge_v2, expected_top3_rate, expected_top5_rate,
               promotion_eligibility_v2, top5_value_signal
        FROM ecse_oddalerts_shadow_monitor
        WHERE final_score IS NULL
          AND promotion_eligibility_v2 IN ('eligible_limited_write_later', 'eligible_shadow_watch')
        ORDER BY kickoff_utc ASC
        LIMIT 5
        """
    ).fetchall()

    new_odds_today = 0
    write_path = Path(f"artifacts/oddalerts_csv_promotion_write_{today_tag}.json")
    if write_path.exists():
        wr = _artifact(write_path)
        new_odds_today = int(wr.get("inserted_count", 0) or 0) + int(wr.get("enriched_count", 0) or 0)

    return {
        "last_pipeline_run": state.get("run_id"),
        "last_pipeline_date": state.get("date"),
        "last_pipeline_recommendation": state.get("final_recommendation"),
        "new_csv_files_today": state.get("files_downloaded", 0),
        "new_odds_snapshots_today": new_odds_today or state.get("odds_snapshots_inserted", 0),
        "live_monitor_records": monitor_total,
        "upcoming_monitor_records": upcoming,
        "waiting_no_snapshot_count": state.get("skipped_reasons", {}).get("no_oddalerts_snapshot", 0),
        "top_eligible_upcoming_signals": [dict(r) for r in eligible_upcoming],
    }
