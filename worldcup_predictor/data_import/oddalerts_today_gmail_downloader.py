"""Today-only OddAlerts Gmail CSV export downloader (owner/internal)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from worldcup_predictor.data_import.oddalerts_gmail_exporter import (
    build_gmail_service,
    fetch_matching_exports,
    sha256_bytes,
    slugify,
)

logger = logging.getLogger(__name__)

PHASE = "ODDALERTS-TODAY-GMAIL-CSV"
INBOX_DIR = Path("data/oddalerts_csv/inbox")
SHA256_INDEX_PATH = Path("artifacts/oddalerts_csv_sha256_index.json")

ECSE_REQUIRED_MARKETS: dict[str, set[str]] = {
    "Fulltime Result Probability": {"home", "draw", "away"},
    "Over/Under 2.5 Probability": {"over_25", "under_25"},
    "Both Teams To Score Probability": {"yes", "no"},
}


@dataclass
class LinkDownloadRecord:
    gmail_message_id: str
    email_timestamp: str
    market: str
    outcome: str
    probability_range: str
    date_from: str
    date_to: str
    csv_filename_from_link: str
    url_redacted: str
    local_path: str = ""
    file_size: int = 0
    sha256: str = ""
    status: str = "pending"
    error: str = ""
    coverage_tag: str = ""


@dataclass
class TodayDownloadSummary:
    date_processed: str
    gmail_query: str
    inbox_path: str
    emails_found: int = 0
    links_found: int = 0
    files_downloaded: int = 0
    files_skipped_duplicate: int = 0
    links_expired: int = 0
    failed_downloads: int = 0
    downloaded_by_market: dict[str, int] = field(default_factory=dict)
    downloaded_by_outcome: dict[str, int] = field(default_factory=dict)
    downloaded_by_date_range: dict[str, int] = field(default_factory=dict)
    records: list[LinkDownloadRecord] = field(default_factory=list)


def build_today_gmail_query(process_date: str) -> str:
    dt = datetime.strptime(process_date, "%Y-%m-%d").date()
    nxt = dt + timedelta(days=1)
    after = f"{dt.year}/{dt.month}/{dt.day}"
    before = f"{nxt.year}/{nxt.month}/{nxt.day}"
    return (
        f'from:joe@oddalerts.com subject:"Your Probability Export is Ready" '
        f"after:{after} before:{before}"
    )


def redact_signed_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?[REDACTED]"


def csv_filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path)
    return Path(path).name or "unknown.csv"


def outcome_slug(outcome: str) -> str:
    text = (outcome or "").strip().rstrip("-").strip()
    slug = slugify(text)
    return re.sub(r"_+$", "", slug) or "unknown"


def market_slug(market: str) -> str:
    return slugify(market or "") or "unknown"


def email_ts_slug(received_at: str, fallback_date: str) -> str:
    try:
        dt = datetime.strptime(received_at, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y%m%d")
    except ValueError:
        return fallback_date.replace("-", "")


def build_today_inbox_filename(
    metadata,
    *,
    process_date: str,
    received_at: str,
    short_hash: str,
) -> str:
    m_slug = market_slug(metadata.market)
    o_slug = outcome_slug(metadata.outcome)
    d_from = metadata.date_from if metadata.date_from != "unknown" else "unknown"
    d_to = metadata.date_to if metadata.date_to != "unknown" else "unknown"
    ts = email_ts_slug(received_at, process_date)
    return f"oddalerts_{m_slug}_{o_slug}_{d_from}_{d_to}_{ts}_{short_hash[:6]}.csv"


def resolve_unique_inbox_path(inbox: Path, filename: str) -> Path:
    dest = inbox / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    n = 1
    while True:
        candidate = inbox / f"{stem}__v{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _is_csv_content(content: bytes, content_type: str | None) -> bool:
    if not content or not content.strip():
        return False
    ct = (content_type or "").lower()
    if "csv" in ct or "text/plain" in ct:
        return True
    head = content[:4096].decode("utf-8", errors="replace").lstrip("\ufeff")
    if head.startswith("ID,") or "Probability (%)" in head[:500]:
        return True
    first_line = head.splitlines()[0] if head.splitlines() else ""
    return "," in first_line


def _is_expired_response(status_code: int, body: bytes) -> bool:
    if status_code in (403, 404, 410):
        return True
    text = body[:2000].decode("utf-8", errors="replace").lower()
    return any(
        m in text
        for m in (
            "expired",
            "request has expired",
            "accessdenied",
            "signaturedoesnotmatch",
            "invalidaccesskeyid",
        )
    )


def load_sha256_index() -> dict[str, str]:
    if not SHA256_INDEX_PATH.is_file():
        return {}
    try:
        return json.loads(SHA256_INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_sha256_index(index: dict[str, str]) -> None:
    SHA256_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHA256_INDEX_PATH.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")


def collect_known_sha256_hashes(*roots: Path) -> dict[str, str]:
    index = load_sha256_index()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.csv"):
            if path.name in ("manifest.csv", "manifest.dry_run.csv"):
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            index.setdefault(digest, str(path))
    return index


def download_csv_safe(url: str, dest: Path, *, timeout: float = 120.0) -> tuple[str, int, str, str]:
    """Returns (status, size, sha256, error). status: ok | EXPIRED | FAILED."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            response = client.get(url)
            body = response.content
            if _is_expired_response(response.status_code, body):
                return "EXPIRED", 0, "", f"HTTP {response.status_code} — link expired or denied"
            if response.status_code != 200:
                return "FAILED", 0, "", f"HTTP {response.status_code}"
            if not _is_csv_content(body, response.headers.get("content-type")):
                return "FAILED", 0, "", "response is not CSV/text"
            if not body.strip():
                return "FAILED", 0, "", "empty file"
            digest = sha256_bytes(body)
            dest.write_bytes(body)
            return "ok", len(body), digest, ""
    except httpx.TimeoutException:
        return "FAILED", 0, "", "timeout"
    except Exception as exc:
        return "FAILED", 0, "", str(exc)


def _normalize_market_label(market: str) -> str:
    text = (market or "").strip()
    lower = text.lower()
    if lower.startswith("fulltime"):
        return "Fulltime Result Probability"
    if "both teams" in lower and "score" in lower:
        return "Both Teams To Score Probability"
    if lower.startswith("over/under 2.5"):
        return "Over/Under 2.5 Probability"
    if text and not text.endswith(" Probability"):
        if lower.startswith("over/under"):
            return f"{text} Probability"
    return text


def _outcome_key(outcome: str) -> str:
    return outcome_slug(outcome)


def build_market_coverage(summary: TodayDownloadSummary) -> dict[str, Any]:
    downloaded_outcomes: dict[str, set[str]] = {}
    by_market: dict[str, dict[str, Any]] = {}

    for rec in summary.records:
        if rec.status != "ok":
            continue
        market = _normalize_market_label(rec.market)
        outcome = _outcome_key(rec.outcome)
        downloaded_outcomes.setdefault(market, set()).add(outcome)
        bucket = by_market.setdefault(
            market,
            {"market": market, "outcomes": {}, "file_count": 0, "files": []},
        )
        bucket["file_count"] += 1
        bucket["outcomes"][outcome] = bucket["outcomes"].get(outcome, 0) + 1
        bucket["files"].append(
            {
                "filename": Path(rec.local_path).name if rec.local_path else "",
                "outcome": rec.outcome,
                "date_range": f"{rec.date_from}..{rec.date_to}",
                "sha256_prefix": rec.sha256[:12] if rec.sha256 else "",
            }
        )

    ecse_status: dict[str, Any] = {}
    for market, required in ECSE_REQUIRED_MARKETS.items():
        have = downloaded_outcomes.get(market, set())
        missing = sorted(required - have)
        ecse_status[market] = {
            "required_outcomes": sorted(required),
            "available_outcomes": sorted(have),
            "missing_outcomes": missing,
            "complete": not missing,
        }

    extras = []
    for market, data in sorted(by_market.items()):
        if market not in ECSE_REQUIRED_MARKETS:
            extras.append(
                {"market": market, "outcomes": sorted(data["outcomes"].keys()), "file_count": data["file_count"]}
            )

    return {
        "phase": PHASE,
        "date_processed": summary.date_processed,
        "ecse_required_markets": ecse_status,
        "all_markets": by_market,
        "extra_markets": extras,
        "ecse_all_complete": all(v["complete"] for v in ecse_status.values()),
    }


def final_recommendation(summary: TodayDownloadSummary, coverage: dict[str, Any]) -> str:
    if summary.emails_found == 0:
        return "NO_TODAY_ODDALERTS_EMAILS_FOUND"
    if summary.links_expired > 0 and summary.files_downloaded == 0:
        return "TODAY_ODDALERTS_LINKS_EXPIRED"
    if summary.files_downloaded == 0 and summary.failed_downloads > 0:
        return "TODAY_ODDALERTS_PARTIAL_DOWNLOAD"
    if summary.files_downloaded == 0:
        return "NO_TODAY_ODDALERTS_EMAILS_FOUND"
    if not coverage.get("ecse_all_complete"):
        return "NEED_MORE_CSV_REQUESTS"
    if summary.failed_downloads > 0 or summary.links_expired > 0:
        return "TODAY_ODDALERTS_PARTIAL_DOWNLOAD"
    return "TODAY_ODDALERTS_CSV_DOWNLOADED"


def run_today_download(
    *,
    process_date: str,
    inbox_dir: Path,
    credentials_path: Path,
    token_path: Path,
    max_messages: int = 500,
    dry_run: bool = False,
    extra_sha_roots: tuple[Path, ...] = (),
) -> TodayDownloadSummary:
    query = build_today_gmail_query(process_date)
    inbox_dir.mkdir(parents=True, exist_ok=True)

    summary = TodayDownloadSummary(
        date_processed=process_date,
        gmail_query=query,
        inbox_path=str(inbox_dir),
    )

    service = build_gmail_service(credentials_path, token_path)
    exports = fetch_matching_exports(service, query=query, max_messages=max_messages)
    summary.emails_found = len(exports)

    sha_index = collect_known_sha256_hashes(
        inbox_dir,
        Path("data/oddalerts_csv/processed"),
        Path("data/oddalerts_csv/raw_archive"),
        Path("data/imports/oddalerts_probability_exports"),
        *extra_sha_roots,
    )

    tmp_path = inbox_dir / "_tmp_download.csv"

    for export in exports:
        if not export.csv_urls:
            rec = LinkDownloadRecord(
                gmail_message_id=export.email_id,
                email_timestamp=export.received_at,
                market=export.metadata.market,
                outcome=export.metadata.outcome,
                probability_range=export.metadata.probability_range,
                date_from=export.metadata.date_from,
                date_to=export.metadata.date_to,
                csv_filename_from_link="",
                url_redacted="",
                status="FAILED",
                error="no CDN link in email body",
            )
            summary.records.append(rec)
            summary.failed_downloads += 1
            continue

        for url in export.csv_urls:
            summary.links_found += 1
            rec = LinkDownloadRecord(
                gmail_message_id=export.email_id,
                email_timestamp=export.received_at,
                market=export.metadata.market,
                outcome=export.metadata.outcome,
                probability_range=export.metadata.probability_range,
                date_from=export.metadata.date_from,
                date_to=export.metadata.date_to,
                csv_filename_from_link=csv_filename_from_url(url),
                url_redacted=redact_signed_url(url),
                coverage_tag=infer_coverage_tag(export.metadata.probability_range),
            )

            if dry_run:
                rec.status = "dry_run"
                summary.records.append(rec)
                continue

            status, size, digest, error = download_csv_safe(url, tmp_path)
            if status == "EXPIRED":
                rec.status = "EXPIRED"
                rec.error = error
                summary.links_expired += 1
                summary.records.append(rec)
                tmp_path.unlink(missing_ok=True)
                continue
            if status != "ok":
                rec.status = "FAILED"
                rec.error = error
                summary.failed_downloads += 1
                summary.records.append(rec)
                tmp_path.unlink(missing_ok=True)
                continue

            if digest in sha_index:
                rec.status = "skipped_duplicate"
                rec.sha256 = digest
                rec.error = f"duplicate of {Path(sha_index[digest]).name}"
                summary.files_skipped_duplicate += 1
                summary.records.append(rec)
                tmp_path.unlink(missing_ok=True)
                continue

            filename = build_today_inbox_filename(
                export.metadata,
                process_date=process_date,
                received_at=export.received_at,
                short_hash=digest,
            )
            dest = resolve_unique_inbox_path(inbox_dir, filename)
            if tmp_path.exists():
                tmp_path.replace(dest)
            rec.local_path = str(dest)
            rec.file_size = size
            rec.sha256 = digest
            rec.status = "ok"
            sha_index[digest] = str(dest)

            market_key = export.metadata.market or "unknown"
            outcome_key = export.metadata.outcome or "unknown"
            range_key = f"{export.metadata.date_from}..{export.metadata.date_to}"
            summary.downloaded_by_market[market_key] = summary.downloaded_by_market.get(market_key, 0) + 1
            summary.downloaded_by_outcome[outcome_key] = summary.downloaded_by_outcome.get(outcome_key, 0) + 1
            summary.downloaded_by_date_range[range_key] = summary.downloaded_by_date_range.get(range_key, 0) + 1
            summary.files_downloaded += 1
            summary.records.append(rec)

            logger.info(
                "Downloaded %s | market=%r outcome=%r | %s bytes",
                dest.name,
                export.metadata.market,
                export.metadata.outcome,
                size,
            )

    if not dry_run:
        save_sha256_index(sha_index)
        tmp_path.unlink(missing_ok=True)

    return summary


def _parse_pct_token(text: str) -> int | None:
    cleaned = (text or "").strip().replace("%", "").strip().rstrip("-").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def classify_probability_band(probability_range: str) -> str:
    pr = (probability_range or "").strip().lower().replace("–", "-")
    if not pr or "-" not in pr:
        return "unknown"
    head, tail = pr.split("-", 1)
    min_pct = _parse_pct_token(head)
    max_pct = _parse_pct_token(tail)
    if min_pct is None or max_pct is None:
        return "unknown"
    if max_pct <= 50 and min_pct == 0:
        return "lower_0_50"
    if max_pct <= 50 and min_pct == 1:
        return "lower_1_50"
    if min_pct >= 50 and max_pct >= 100:
        return "upper_50_100"
    if min_pct in (0, 1) and max_pct >= 100:
        return "full_range"
    return "unknown"


def infer_coverage_tag(probability_range: str) -> str:
    band = classify_probability_band(probability_range)
    if band in ("lower_0_50", "lower_1_50"):
        return "ecse_lower_band"
    if band == "full_range":
        return "ecse_complete"
    if band == "upper_50_100":
        return "partial_50_100"
    return "unknown"


def summary_to_json(summary: TodayDownloadSummary, *, default_coverage_tag: str = "") -> dict[str, Any]:
    return {
        "phase": PHASE,
        "date_processed": summary.date_processed,
        "gmail_query": summary.gmail_query,
        "emails_found": summary.emails_found,
        "links_found": summary.links_found,
        "files_downloaded": summary.files_downloaded,
        "files_skipped_duplicate": summary.files_skipped_duplicate,
        "links_expired": summary.links_expired,
        "failed_downloads": summary.failed_downloads,
        "downloaded_by_market": summary.downloaded_by_market,
        "downloaded_by_outcome": summary.downloaded_by_outcome,
        "downloaded_by_date_range": summary.downloaded_by_date_range,
        "inbox_path": summary.inbox_path,
        "records": [
            {
                "gmail_message_id": r.gmail_message_id,
                "email_timestamp": r.email_timestamp,
                "market": r.market,
                "outcome": r.outcome,
                "probability_range": r.probability_range,
                "coverage_tag": r.coverage_tag or default_coverage_tag or infer_coverage_tag(r.probability_range),
                "date_from": r.date_from,
                "date_to": r.date_to,
                "csv_filename_from_link": r.csv_filename_from_link,
                "url_redacted": r.url_redacted,
                "local_path": r.local_path,
                "file_size": r.file_size,
                "sha256_prefix": r.sha256[:12] if r.sha256 else "",
                "status": r.status,
                "error": r.error,
            }
            for r in summary.records
        ],
    }


def artifact_paths(process_date: str) -> tuple[Path, Path]:
    ymd = process_date.replace("-", "")
    return (
        Path(f"artifacts/oddalerts_today_gmail_csv_download_summary_{ymd}.json"),
        Path(f"artifacts/oddalerts_today_gmail_market_coverage_{ymd}.json"),
    )


def lower_band_artifact_paths(process_date: str) -> tuple[Path, Path]:
    ymd = process_date.replace("-", "")
    return (
        Path(f"artifacts/oddalerts_lower_band_gmail_download_summary_{ymd}.json"),
        Path(f"artifacts/oddalerts_lower_band_ecse_market_coverage_{ymd}.json"),
    )


ECSE_OUTCOME_TO_KEY: dict[tuple[str, str], str] = {
    ("Fulltime Result Probability", "home"): "match_result_home",
    ("Fulltime Result Probability", "draw"): "match_result_draw",
    ("Fulltime Result Probability", "away"): "match_result_away",
    ("Over/Under 2.5 Probability", "over_25"): "goals_over_2_5",
    ("Over/Under 2.5 Probability", "under_25"): "goals_under_2_5",
    ("Both Teams To Score Probability", "yes"): "btts_yes",
    ("Both Teams To Score Probability", "no"): "btts_no",
}


def _outcome_matches(record_outcome: str, expected: str) -> bool:
    ro = _outcome_key(record_outcome)
    ex = _outcome_key(expected)
    return ro == ex or ro.replace("_", "") == ex.replace("_", "")


def build_lower_band_download_summary(summary: TodayDownloadSummary) -> dict[str, Any]:
    lower_downloaded = 0
    lower_duplicate = 0
    upper_duplicate = 0
    unrelated = 0
    lower_band_emails = 0
    by_band: dict[str, int] = {}

    for rec in summary.records:
        band = classify_probability_band(rec.probability_range)
        by_band[band] = by_band.get(band, 0) + 1
        if band in ("lower_0_50", "lower_1_50"):
            lower_band_emails += 1
            if rec.status == "ok":
                lower_downloaded += 1
            elif rec.status == "skipped_duplicate":
                lower_duplicate += 1
        elif band == "upper_50_100":
            if rec.status == "skipped_duplicate":
                upper_duplicate += 1
        else:
            unrelated += 1

    return {
        "phase": "ODDALERTS-LOWER-BAND-GMAIL",
        "date_processed": summary.date_processed,
        "gmail_query": summary.gmail_query,
        "emails_found": summary.emails_found,
        "links_found": summary.links_found,
        "lower_band_emails": lower_band_emails,
        "lower_band_downloaded": lower_downloaded,
        "lower_band_duplicates_skipped": lower_duplicate,
        "upper_band_duplicates_skipped": upper_duplicate,
        "unrelated_or_other_exports": unrelated,
        "files_downloaded_total": summary.files_downloaded,
        "files_skipped_duplicate_total": summary.files_skipped_duplicate,
        "links_expired": summary.links_expired,
        "failed_downloads": summary.failed_downloads,
        "probability_band_counts": by_band,
        "records": [
            {
                "market": r.market,
                "outcome": r.outcome,
                "probability_range": r.probability_range,
                "probability_band": classify_probability_band(r.probability_range),
                "coverage_tag": r.coverage_tag or infer_coverage_tag(r.probability_range),
                "date_from": r.date_from,
                "date_to": r.date_to,
                "email_timestamp": r.email_timestamp,
                "status": r.status,
                "sha256_prefix": r.sha256[:12] if r.sha256 else "",
                "local_path": Path(r.local_path).name if r.local_path else "",
            }
            for r in summary.records
        ],
    }


def build_lower_band_ecse_market_coverage(summary: TodayDownloadSummary) -> dict[str, Any]:
    coverage: dict[str, dict[str, Any]] = {}

    for (market, outcome), normalized_key in ECSE_OUTCOME_TO_KEY.items():
        matching = [
            r
            for r in summary.records
            if _normalize_market_label(r.market) == _normalize_market_label(market)
            and _outcome_matches(r.outcome, outcome)
        ]
        status = "MISSING"
        band_found = None
        file_status = None

        for rec in matching:
            band = classify_probability_band(rec.probability_range)
            if band == "lower_0_50" and rec.status == "ok":
                status = "FOUND_0_50"
                band_found = band
                file_status = rec.status
                break
            if band == "lower_1_50" and rec.status == "ok":
                status = "FOUND_1_50"
                band_found = band
                file_status = rec.status
                break

        if status == "MISSING":
            for rec in matching:
                band = classify_probability_band(rec.probability_range)
                if band in ("lower_0_50", "lower_1_50") and rec.status == "skipped_duplicate":
                    status = "DUPLICATE_SKIPPED"
                    band_found = band
                    file_status = rec.status
                    break

        if status == "MISSING" and matching:
            upper_only = all(
                classify_probability_band(r.probability_range) == "upper_50_100" for r in matching
            )
            if upper_only:
                status = "FOUND_50_100_ONLY"
                band_found = "upper_50_100"
                file_status = matching[0].status

        coverage[normalized_key] = {
            "export_market": market,
            "export_outcome": outcome,
            "normalized_key": normalized_key,
            "status": status,
            "probability_band": band_found,
            "file_status": file_status,
            "matching_email_count": len(matching),
        }

    found_lower = sum(1 for v in coverage.values() if v["status"] in ("FOUND_0_50", "FOUND_1_50"))
    return {
        "phase": "ODDALERTS-LOWER-BAND-GMAIL",
        "date_processed": summary.date_processed,
        "ecse_outcomes_required": 7,
        "found_lower_band": found_lower,
        "all_lower_band_present": found_lower == 7,
        "outcomes": coverage,
    }


def lower_band_final_recommendation(summary: TodayDownloadSummary, lb_coverage: dict[str, Any]) -> str:
    lb = build_lower_band_download_summary(summary)
    if summary.emails_found == 0:
        return "DOWNLOAD_FAILED"
    if summary.links_expired > 0 and lb["lower_band_downloaded"] == 0 and lb["lower_band_duplicates_skipped"] == 0:
        return "DOWNLOAD_FAILED"
    if lb["lower_band_downloaded"] == 0 and lb["lower_band_duplicates_skipped"] == 0:
        if lb["upper_band_duplicates_skipped"] > 0:
            return "ONLY_DUPLICATES_FOUND"
        return "MISSING_LOWER_BAND_MARKETS"
    if not lb_coverage.get("all_lower_band_present"):
        dup = sum(1 for v in lb_coverage["outcomes"].values() if v["status"] == "DUPLICATE_SKIPPED")
        if dup == 7:
            return "ONLY_DUPLICATES_FOUND"
        return "MISSING_LOWER_BAND_MARKETS"
    if summary.failed_downloads > 0:
        return "DO_NOT_PROMOTE_YET"
    return "ODDALERTS_LOWER_BAND_IMPORTED"


def build_ecse_dual_band_market_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess ECSE outcome coverage across probability bands (Gmail records)."""
    coverage: dict[str, dict[str, Any]] = {}

    for (market, outcome), normalized_key in ECSE_OUTCOME_TO_KEY.items():
        matching = [
            r
            for r in records
            if _normalize_market_label(str(r.get("market") or "")) == _normalize_market_label(market)
            and _outcome_matches(str(r.get("outcome") or ""), outcome)
        ]
        bands = {"lower_0_50": False, "lower_1_50": False, "upper_50_100": False, "full_range": False}
        for r in matching:
            if r.get("status") not in ("ok", "skipped_duplicate"):
                continue
            band = classify_probability_band(str(r.get("probability_range") or ""))
            if band in bands:
                bands[band] = True

        has_lower = bands["lower_0_50"] or bands["lower_1_50"]
        has_upper = bands["upper_50_100"]
        has_full = bands["full_range"]

        if has_full:
            status = "COMPLETE_FULL_RANGE"
        elif has_upper and has_lower:
            status = "HAS_UPPER_AND_LOWER_BANDS"
        elif has_upper:
            status = "HAS_UPPER_ONLY"
        elif has_lower:
            status = "HAS_LOWER_ONLY"
        else:
            status = "MISSING"

        coverage[normalized_key] = {
            "export_market": market,
            "export_outcome": outcome,
            "normalized_key": normalized_key,
            "status": status,
            "bands_present": bands,
            "matching_email_count": len(matching),
        }

    complete = sum(
        1
        for v in coverage.values()
        if v["status"] in ("COMPLETE_FULL_RANGE", "HAS_UPPER_AND_LOWER_BANDS")
    )
    return {
        "phase": "ODDALERTS-LOWER-BAND-GMAIL",
        "ecse_outcomes_required": 7,
        "complete_dual_band_count": complete,
        "all_complete": complete == 7,
        "outcomes": coverage,
    }


def build_ecse_dual_band_market_coverage_from_summary(summary: TodayDownloadSummary) -> dict[str, Any]:
    payload = summary_to_json(summary, default_coverage_tag="ecse_lower_band")
    return build_ecse_dual_band_market_coverage(payload.get("records") or [])
