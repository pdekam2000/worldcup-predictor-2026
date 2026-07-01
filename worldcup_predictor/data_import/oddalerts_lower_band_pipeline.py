"""OddAlerts lower-band watch + import pipeline (owner/internal)."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_lower_band_watcher import (
    run_lower_band_watch,
    watch_artifact_path,
    watch_final_recommendation,
)

logger = logging.getLogger(__name__)

PHASE = "ODDALERTS-LOWER-BAND-WATCH-PIPELINE"
REPORT_PATH = Path("ODDALERTS_LOWER_BAND_WATCH_AND_IMPORT_REPORT.md")
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


@dataclass
class DbSnapshot:
    probability_row_count: int = 0
    ready_full: int = 0
    ready_partial: int = 0
    odds_snapshots: int = 0
    ecse_snapshots: int = 0
    wde_predictions: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "probability_row_count": self.probability_row_count,
            "ready_full": self.ready_full,
            "ready_partial": self.ready_partial,
            "odds_snapshots": self.odds_snapshots,
            "ecse_snapshots": self.ecse_snapshots,
            "wde_predictions": self.wde_predictions,
        }


@dataclass
class PipelineResult:
    process_date: str
    watch_artifact: dict[str, Any] = field(default_factory=dict)
    baseline: DbSnapshot = field(default_factory=DbSnapshot)
    after: DbSnapshot = field(default_factory=DbSnapshot)
    import_ran: bool = False
    script_results: list[dict[str, Any]] = field(default_factory=list)
    validation_artifacts: dict[str, Any] = field(default_factory=dict)
    final_recommendation: str = "DO_NOT_PROMOTE_YET"

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": PHASE,
            "process_date": self.process_date,
            "watch_artifact_path": str(watch_artifact_path(self.process_date)),
            "import_ran": self.import_ran,
            "baseline": self.baseline.to_dict(),
            "after": self.after.to_dict(),
            "script_results": self.script_results,
            "final_recommendation": self.final_recommendation,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _date_tag(process_date: str) -> str:
    return process_date.replace("-", "")


def _artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_db_snapshot(process_date: str) -> DbSnapshot:
    tag = _date_tag(process_date)
    ecse_path = Path(f"artifacts/oddalerts_policy_ecse_readiness_{tag}.json")
    ecse = _artifact(ecse_path)
    status_counts = ecse.get("status_counts") or {}

    conn = connect(get_settings().sqlite_path)
    snap = DbSnapshot(
        probability_row_count=int(
            conn.execute("SELECT COUNT(*) c FROM oddalerts_probability_market_rows").fetchone()["c"]
        ),
        ready_full=int(status_counts.get("READY_FULL", ecse.get("ready_full_count", 0)) or 0),
        ready_partial=int(status_counts.get("READY_PARTIAL", ecse.get("ready_partial_count", 0)) or 0),
        odds_snapshots=int(conn.execute("SELECT COUNT(*) c FROM odds_snapshots").fetchone()["c"]),
        ecse_snapshots=int(conn.execute("SELECT COUNT(*) c FROM ecse_prediction_snapshots").fetchone()["c"]),
        wde_predictions=int(conn.execute("SELECT COUNT(*) c FROM worldcup_stored_predictions").fetchone()["c"]),
    )
    conn.close()
    return snap


def _run_script(script_name: str, *args: str) -> dict[str, Any]:
    cmd = [sys.executable, str(SCRIPTS / script_name), *args]
    logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    result = {
        "script": script_name,
        "args": list(args),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }
    if proc.returncode != 0:
        logger.warning("%s exited %s", script_name, proc.returncode)
    return result


POST_STABLE_SCRIPTS: list[tuple[str, list[str]]] = [
    ("import_oddalerts_csv_incremental.py", ["--input-dir", "data/oddalerts_csv/inbox"]),
    ("audit_oddalerts_csv_all_markets.py", []),
    ("validate_oddalerts_all_market_mapping.py", []),
    ("crosswalk_oddalerts_probability_csv_to_fixtures.py", []),
    ("build_oddalerts_policy_market_matrix.py", []),
    ("preview_oddalerts_policy_to_odds_snapshots.py", []),
    ("validate_oddalerts_bookmaker_policy.py", []),
    ("validate_oddalerts_ecse_complete_coverage.py", []),
]


def run_post_stable_import_pipeline() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for script, args in POST_STABLE_SCRIPTS:
        results.append(_run_script(script, *args))
    return results


def _load_validation_artifacts(process_date: str) -> dict[str, Any]:
    tag = _date_tag(process_date)
    return {
        "watch": _artifact(watch_artifact_path(process_date)),
        "ecse_market_coverage": _artifact(Path(f"artifacts/oddalerts_lower_band_ecse_market_coverage_{tag}.json")),
        "policy_ecse_readiness": _artifact(Path(f"artifacts/oddalerts_policy_ecse_readiness_{tag}.json")),
        "policy_preview": _artifact(Path(f"artifacts/oddalerts_policy_odds_snapshot_preview_{tag}.json")),
        "bookmaker_validation": _artifact(Path(f"artifacts/oddalerts_bookmaker_policy_validation_{tag}.json")),
        "ecse_complete_validation": _artifact(
            Path(f"artifacts/oddalerts_ecse_complete_coverage_validation_{tag}.json")
        ),
        "all_market_validation": _artifact(Path(f"artifacts/oddalerts_all_market_mapping_validation_{tag}.json")),
        "import_summary": _artifact(Path("artifacts/oddalerts_csv_incremental_import_summary.json")),
    }


def pipeline_final_recommendation(
    *,
    watch: dict[str, Any],
    baseline: DbSnapshot,
    after: DbSnapshot,
    import_ran: bool,
    validation: dict[str, Any],
) -> str:
    watch_rec = watch_final_recommendation(watch)
    stop = watch.get("stop_reason")

    if stop != "stable_rounds_reached":
        if watch.get("total_failed", 0) > 0 and watch.get("total_new_files_downloaded", 0) == 0:
            return "DOWNLOAD_FAILED"
        return "STILL_WAITING_FOR_EMAILS"

    if not import_ran:
        return watch_rec

    cov = validation.get("ecse_market_coverage") or {}
    outcomes = cov.get("outcomes") or {}
    statuses = [v.get("status") for v in outcomes.values() if isinstance(v, dict)]
    missing = [k for k, v in outcomes.items() if isinstance(v, dict) and v.get("status") == "MISSING"]

    if missing:
        return "MISSING_LOWER_BAND_MARKETS"

    ecse_val = validation.get("ecse_complete_validation") or {}
    book_val = validation.get("bookmaker_validation") or {}
    preview = validation.get("policy_preview") or {}
    policy = validation.get("policy_ecse_readiness") or {}

    ready_full = int((policy.get("status_counts") or {}).get("READY_FULL", after.ready_full))
    would_insert = int(preview.get("would_insert_count", preview.get("insert_count", 0)) or 0)

    book_passed = False
    if isinstance(book_val.get("checks"), list):
        book_passed = all(c.get("passed") for c in book_val["checks"])

    ecse_rec = ecse_val.get("final_recommendation", "")
    dual_complete = cov.get("all_complete") or (
        statuses and all(s in ("COMPLETE_FULL_RANGE", "HAS_UPPER_AND_LOWER_BANDS") for s in statuses)
    )

    if watch.get("total_new_files_downloaded", 0) == 0:
        if watch.get("total_duplicates_skipped", 0) > 0:
            return "ONLY_DUPLICATES_FOUND"
        return "MISSING_LOWER_BAND_MARKETS"

    if dual_complete and ready_full > 0 and would_insert > 0 and book_passed:
        if ecse_rec in ("READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN", "ODDALERTS_COMPLETE_COVERAGE_READY"):
            return "READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN"
        return "READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN"

    if dual_complete:
        return "ODDALERTS_COMPLETE_COVERAGE_READY"

    if after.ready_full > baseline.ready_full or after.probability_row_count > baseline.probability_row_count:
        return "ODDALERTS_LOWER_BAND_IMPORTED"

    return watch_rec if watch_rec != "STILL_WAITING_FOR_EMAILS" else "DO_NOT_PROMOTE_YET"


def build_report_markdown(result: PipelineResult, validation: dict[str, Any]) -> str:
    watch = result.watch_artifact
    rounds = watch.get("rounds") or []
    cov = validation.get("ecse_market_coverage") or {}
    outcomes = cov.get("outcomes") or {}
    policy = validation.get("policy_ecse_readiness") or {}
    preview = validation.get("policy_preview") or {}
    ecse_val = validation.get("ecse_complete_validation") or {}
    book_val = validation.get("bookmaker_validation") or {}
    map_val = validation.get("all_market_validation") or {}

    round_lines = []
    for r in rounds:
        round_lines.append(
            f"| {r.get('round_number')} | {r.get('files_downloaded', 0)} | "
            f"{r.get('duplicates_skipped', 0)} | {r.get('failed_downloads', 0)} | "
            f"{r.get('links_expired', 0)} | {r.get('new_sha256_count', 0)} | "
            f"{'yes' if r.get('stable_after_round') else 'no'} |"
        )

    outcome_lines = []
    for key, info in sorted(outcomes.items()):
        if not isinstance(info, dict):
            continue
        bands = info.get("bands_present") or {}
        band_str = ", ".join(k for k, v in bands.items() if v) or "none"
        outcome_lines.append(f"| {key} | {info.get('status', '?')} | {band_str} |")

    missing = [k for k, v in outcomes.items() if isinstance(v, dict) and v.get("status") == "MISSING"]

    checks_summary = []
    for label, val in (
        ("Bookmaker policy", book_val),
        ("All-market mapping", map_val),
        ("ECSE complete coverage", ecse_val),
    ):
        if val.get("checks"):
            passed = sum(1 for c in val["checks"] if c.get("passed"))
            total = len(val["checks"])
            checks_summary.append(f"- **{label}:** {passed}/{total} checks passed")
        elif val:
            checks_summary.append(f"- **{label}:** artifact present")

    would_insert = preview.get("would_insert_count", preview.get("insert_count", "n/a"))
    dryrun_ready = result.final_recommendation == "READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN"

    return f"""# OddAlerts Lower-Band Watch and Import Report

**Phase:** {PHASE}  
**Date:** {result.process_date}  
**Generated:** {_utc_now()}  
**Mode:** Owner/internal — Gmail watch, incremental import, readiness recheck — no odds_snapshots writes, no ECSE generation

---

## Summary

Watcher monitored Gmail for OddAlerts lower-band CSV exports, then {'ran' if result.import_ran else 'skipped'} import + readiness pipeline after `{watch.get('stop_reason', 'unknown')}`.

**Final recommendation:** `{result.final_recommendation}`

---

## Part A — Watch rounds

**Artifact:** `{watch_artifact_path(result.process_date)}`  
**Gmail query:** `{watch.get('gmail_query', '')}`  
**Stop reason:** `{watch.get('stop_reason')}`  
**Stable rounds:** {watch.get('stable_rounds_observed', 0)} / {watch.get('stable_rounds_required', 0)} required

| Round | New files | Duplicates skipped | Failed | Expired | New sha256 | Stable |
|-------|-----------|-------------------|--------|---------|------------|--------|
{chr(10).join(round_lines) if round_lines else '| — | — | — | — | — | — | — |'}

**Totals:** {watch.get('total_new_files_downloaded', 0)} new files, {watch.get('total_duplicates_skipped', 0)} duplicates skipped, {watch.get('total_failed', 0)} failed, {watch.get('total_expired', 0)} expired links

---

## Part B — Lower-band market coverage (Gmail)

**Artifact:** `artifacts/oddalerts_lower_band_ecse_market_coverage_{_date_tag(result.process_date)}.json`

| Outcome | Status | Bands present |
|---------|--------|---------------|
{chr(10).join(outcome_lines) if outcome_lines else '| — | — | — |'}

Dual-band complete: **{cov.get('complete_dual_band_count', 0)}/7**

---

## Part C — Import + readiness

**Import ran:** {result.import_ran}

| Metric | Before | After |
|--------|--------|-------|
| Probability rows | {result.baseline.probability_row_count:,} | {result.after.probability_row_count:,} |
| ECSE READY_FULL | {result.baseline.ready_full} | {result.after.ready_full} |
| ECSE READY_PARTIAL | {result.baseline.ready_partial} | {result.after.ready_partial} |
| odds_snapshots (unchanged) | {result.baseline.odds_snapshots} | {result.after.odds_snapshots} |
| ecse_prediction_snapshots (unchanged) | {result.baseline.ecse_snapshots} | {result.after.ecse_snapshots} |

**Policy preview would_insert:** {would_insert} (dry-run only — not executed)

---

## Part D — Validation

{chr(10).join(checks_summary) if checks_summary else '- No validation artifacts loaded'}

**Remaining missing outcomes:** {', '.join(missing) if missing else 'none'}

---

## Part E — Odds snapshot promotion dry-run readiness

{'**Ready for odds snapshot promotion dry-run.**' if dryrun_ready else '**Not ready for promotion dry-run yet.**'}

Policy READY_FULL fixtures: {result.after.ready_full}

---

## Script execution log

| Script | Exit code |
|--------|-----------|
{chr(10).join(f"| {s['script']} | {s['returncode']} |" for s in result.script_results) if result.script_results else '| — | — |'}
"""


def run_lower_band_watch_pipeline(
    *,
    process_date: str,
    check_interval_minutes: int = 10,
    stable_rounds: int = 2,
    max_rounds: int = 12,
    inbox_dir: Path | None = None,
    credentials_path: Path | None = None,
    token_path: Path | None = None,
    max_messages: int = 500,
    dry_run: bool = False,
    skip_watch: bool = False,
) -> PipelineResult:
    baseline = collect_db_snapshot(process_date)
    result = PipelineResult(process_date=process_date, baseline=baseline)

    if skip_watch and watch_artifact_path(process_date).exists():
        result.watch_artifact = _artifact(watch_artifact_path(process_date))
        logger.info("Loaded existing watch artifact (skip_watch)")
    else:
        result.watch_artifact = run_lower_band_watch(
            process_date=process_date,
            check_interval_minutes=check_interval_minutes,
            stable_rounds=stable_rounds,
            max_rounds=max_rounds,
            inbox_dir=inbox_dir,
            credentials_path=credentials_path,
            token_path=token_path,
            max_messages=max_messages,
            dry_run=dry_run,
        )

    watch_rec = watch_final_recommendation(result.watch_artifact)
    result.watch_artifact["watch_recommendation"] = watch_rec

    if result.watch_artifact.get("stop_reason") == "stable_rounds_reached" and not dry_run:
        result.import_ran = True
        result.script_results = run_post_stable_import_pipeline()
        result.after = collect_db_snapshot(process_date)
    else:
        result.after = collect_db_snapshot(process_date)

    validation = _load_validation_artifacts(process_date)
    result.validation_artifacts = {k: bool(v) for k, v in validation.items()}
    result.final_recommendation = pipeline_final_recommendation(
        watch=result.watch_artifact,
        baseline=baseline,
        after=result.after,
        import_ran=result.import_ran,
        validation=validation,
    )

    report_md = build_report_markdown(result, validation)
    REPORT_PATH.write_text(report_md, encoding="utf-8")

    artifact_out = Path(f"artifacts/oddalerts_lower_band_watch_pipeline_{_date_tag(process_date)}.json")
    artifact_out.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["finished_at_utc"] = _utc_now()
    payload["report_path"] = str(REPORT_PATH)
    artifact_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    return result
