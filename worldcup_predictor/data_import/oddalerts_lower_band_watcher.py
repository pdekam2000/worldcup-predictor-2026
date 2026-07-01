"""OddAlerts lower-band Gmail watch workflow (owner/internal)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.data_import.oddalerts_today_gmail_downloader import (
    INBOX_DIR,
    TodayDownloadSummary,
    build_ecse_dual_band_market_coverage,
    build_lower_band_download_summary,
    build_lower_band_ecse_market_coverage,
    build_today_gmail_query,
    classify_probability_band,
    lower_band_artifact_paths,
    run_today_download,
    summary_to_json,
)

logger = logging.getLogger(__name__)

PHASE = "ODDALERTS-LOWER-BAND-WATCH"
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREDENTIALS = _ROOT / "credentials" / "gmail_oauth_client.json"
DEFAULT_TOKEN = _ROOT / "data" / "imports" / "oddalerts_probability_exports" / ".gmail_token.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def watch_artifact_path(process_date: str) -> Path:
    ymd = process_date.replace("-", "")
    return Path(f"artifacts/oddalerts_lower_band_watch_{ymd}.json")


@dataclass
class WatchRoundResult:
    round_number: int
    started_at_utc: str
    finished_at_utc: str
    emails_found: int = 0
    links_found: int = 0
    lower_band_emails: int = 0
    files_downloaded: int = 0
    duplicates_skipped: int = 0
    failed_downloads: int = 0
    links_expired: int = 0
    new_sha256_count: int = 0
    probability_band_counts: dict[str, int] = field(default_factory=dict)
    stable_after_round: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_number": self.round_number,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "emails_found": self.emails_found,
            "links_found": self.links_found,
            "lower_band_emails": self.lower_band_emails,
            "files_downloaded": self.files_downloaded,
            "duplicates_skipped": self.duplicates_skipped,
            "failed_downloads": self.failed_downloads,
            "links_expired": self.links_expired,
            "new_sha256_count": self.new_sha256_count,
            "probability_band_counts": self.probability_band_counts,
            "stable_after_round": self.stable_after_round,
        }


def _record_key(rec: dict[str, Any]) -> str:
    sha = rec.get("sha256_prefix") or rec.get("sha256") or ""
    mid = rec.get("gmail_message_id") or ""
    return f"{mid}:{sha}:{rec.get('market')}:{rec.get('outcome')}"


def _merge_records(existing: list[dict[str, Any]], summary: TodayDownloadSummary) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {_record_key(r): r for r in existing}
    payload = summary_to_json(summary, default_coverage_tag="ecse_lower_band")
    for rec in payload.get("records") or []:
        rec = dict(rec)
        rec["probability_band"] = classify_probability_band(rec.get("probability_range", ""))
        by_key[_record_key(rec)] = rec
    return list(by_key.values())


def run_lower_band_watch(
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
) -> dict[str, Any]:
    inbox = inbox_dir or INBOX_DIR
    creds = credentials_path or DEFAULT_CREDENTIALS
    token = token_path or DEFAULT_TOKEN
    query = build_today_gmail_query(process_date)

    started_at = _utc_now()
    rounds: list[dict[str, Any]] = []
    accumulated_records: list[dict[str, Any]] = []
    seen_sha256: set[str] = set()
    stable_count = 0
    total_new_files = 0
    total_duplicates = 0
    total_failed = 0
    total_expired = 0
    stop_reason = "max_rounds_reached"

    for round_num in range(1, max_rounds + 1):
        round_started = _utc_now()
        logger.info("Watch round %s/%s starting", round_num, max_rounds)

        summary = run_today_download(
            process_date=process_date,
            inbox_dir=inbox.resolve(),
            credentials_path=creds.resolve(),
            token_path=token.resolve(),
            max_messages=max_messages,
            dry_run=dry_run,
        )

        lb = build_lower_band_download_summary(summary)
        new_sha_this_round = 0
        for rec in summary.records:
            if rec.status == "ok" and rec.sha256:
                if rec.sha256 not in seen_sha256:
                    seen_sha256.add(rec.sha256)
                    new_sha_this_round += 1

        accumulated_records = _merge_records(accumulated_records, summary)

        round_result = WatchRoundResult(
            round_number=round_num,
            started_at_utc=round_started,
            finished_at_utc=_utc_now(),
            emails_found=summary.emails_found,
            links_found=summary.links_found,
            lower_band_emails=lb.get("lower_band_emails", 0),
            files_downloaded=summary.files_downloaded,
            duplicates_skipped=summary.files_skipped_duplicate,
            failed_downloads=summary.failed_downloads,
            links_expired=summary.links_expired,
            new_sha256_count=new_sha_this_round,
            probability_band_counts=lb.get("probability_band_counts", {}),
        )

        total_new_files += summary.files_downloaded
        total_duplicates += summary.files_skipped_duplicate
        total_failed += summary.failed_downloads
        total_expired += summary.links_expired

        if summary.files_downloaded == 0:
            stable_count += 1
            round_result.stable_after_round = True
            logger.info(
                "Round %s stable (0 new files). stable_count=%s/%s",
                round_num,
                stable_count,
                stable_rounds,
            )
        else:
            stable_count = 0
            logger.info("Round %s downloaded %s new files", round_num, summary.files_downloaded)

        rounds.append(round_result.to_dict())

        # Refresh per-round lower-band summary artifacts
        if not dry_run:
            lb_summary = build_lower_band_download_summary(summary)
            lb_summary["watch_round"] = round_num
            lb_coverage = build_lower_band_ecse_market_coverage(summary)
            lb_summary_path, lb_coverage_path = lower_band_artifact_paths(process_date)
            lb_summary_path.parent.mkdir(parents=True, exist_ok=True)
            lb_summary_path.write_text(json.dumps(lb_summary, indent=2, ensure_ascii=False), encoding="utf-8")
            lb_coverage_path.write_text(json.dumps(lb_coverage, indent=2, ensure_ascii=False), encoding="utf-8")

        if stable_count >= stable_rounds:
            stop_reason = "stable_rounds_reached"
            logger.info("Stopping watch: %s", stop_reason)
            break

        if round_num < max_rounds and stable_count < stable_rounds:
            sleep_s = max(1, check_interval_minutes * 60)
            logger.info("Sleeping %s minutes until next check", check_interval_minutes)
            time.sleep(sleep_s)

    dual_coverage = build_ecse_dual_band_market_coverage(accumulated_records)

    artifact = {
        "phase": PHASE,
        "date_processed": process_date,
        "gmail_query": query,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "rounds_run": len(rounds),
        "stable_rounds_required": stable_rounds,
        "stable_rounds_observed": stable_count,
        "check_interval_minutes": check_interval_minutes,
        "max_rounds": max_rounds,
        "total_new_files_downloaded": total_new_files,
        "total_duplicates_skipped": total_duplicates,
        "total_failed": total_failed,
        "total_expired": total_expired,
        "total_unique_sha256": len(seen_sha256),
        "lower_band_market_coverage": dual_coverage,
        "rounds": rounds,
        "stop_reason": stop_reason,
    }

    out_path = watch_artifact_path(process_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    # Final dual-band ECSE coverage artifact (Part E statuses)
    _, lb_cov_path = lower_band_artifact_paths(process_date)
    dual_coverage["watch_stop_reason"] = stop_reason
    dual_coverage["generated_at_utc"] = _utc_now()
    lb_cov_path.write_text(json.dumps(dual_coverage, indent=2, ensure_ascii=False), encoding="utf-8")

    return artifact


def watch_final_recommendation(artifact: dict[str, Any]) -> str:
    stop = artifact.get("stop_reason")
    cov = artifact.get("lower_band_market_coverage") or {}
    outcomes = (cov.get("outcomes") or {}) if isinstance(cov, dict) else {}
    statuses = [v.get("status") for v in outcomes.values() if isinstance(v, dict)]

    if stop != "stable_rounds_reached":
        if artifact.get("total_failed", 0) > 0 and artifact.get("total_new_files_downloaded", 0) == 0:
            return "DOWNLOAD_FAILED"
        return "STILL_WAITING_FOR_EMAILS"

    if artifact.get("total_new_files_downloaded", 0) == 0:
        if artifact.get("total_duplicates_skipped", 0) > 0:
            return "ONLY_DUPLICATES_FOUND"
        return "MISSING_LOWER_BAND_MARKETS"

    if statuses and all(s in ("COMPLETE_FULL_RANGE", "HAS_UPPER_AND_LOWER_BANDS") for s in statuses):
        return "ODDALERTS_COMPLETE_COVERAGE_READY"

    if statuses and all(s != "MISSING" for s in statuses):
        return "ODDALERTS_LOWER_BAND_IMPORTED"

    if any(s == "MISSING" for s in statuses):
        return "MISSING_LOWER_BAND_MARKETS"

    return "DO_NOT_PROMOTE_YET"
