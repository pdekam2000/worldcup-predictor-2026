"""Read-only Gmail → OddAlerts probability CSV export downloader (library)."""

from __future__ import annotations

import base64
import csv
import hashlib
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_SEARCH_QUERY = (
    'from:joe@oddalerts.com subject:"Your Probability Export is Ready" newer_than:7d'
)
CDN_HOST = "oddalertscdn.fra1.digitaloceanspaces.com"
CDN_URL_RE = re.compile(
    rf"https?://{re.escape(CDN_HOST)}[^\s\"'<>)\]]+",
    re.IGNORECASE,
)
HREF_CDN_RE = re.compile(
    rf'href=["\'](https?://{re.escape(CDN_HOST)}[^"\']+)["\']',
    re.IGNORECASE,
)

MANIFEST_COLUMNS = [
    "email_id",
    "received_at",
    "market",
    "outcome",
    "probability_range",
    "date_from",
    "date_to",
    "original_url",
    "local_path",
    "file_size",
    "sha256",
    "download_status",
    "error",
]

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


@dataclass
class ExportMetadata:
    market: str = "unknown"
    outcome: str = "unknown"
    probability_range: str = "unknown"
    date_from: str = "unknown"
    date_to: str = "unknown"
    date_range_raw: str = ""


@dataclass
class EmailExport:
    email_id: str
    received_at: str
    metadata: ExportMetadata
    csv_urls: list[str] = field(default_factory=list)
    body_preview: str = ""


@dataclass
class DownloadResult:
    email_id: str
    received_at: str
    metadata: ExportMetadata
    original_url: str
    local_path: str = ""
    file_size: int = 0
    sha256: str = ""
    download_status: str = "pending"
    error: str = ""


@dataclass
class RunSummary:
    emails_found: int = 0
    links_found: int = 0
    files_downloaded: int = 0
    failed_links: int = 0
    skipped_links: int = 0
    total_size_bytes: int = 0
    dry_run: bool = True


def slugify(value: str, *, max_len: int = 80) -> str:
    text = html.unescape(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return "unknown"
    return text[:max_len].rstrip("_")


def _strip_html(text: str) -> str:
    decoded = html.unescape(text)
    decoded = TAG_RE.sub(" ", decoded)
    decoded = WS_RE.sub(" ", decoded)
    return decoded.strip()


def _label_value(text: str, labels: Iterable[str]) -> str | None:
    plain = _strip_html(text)
    for label in labels:
        pattern = re.compile(
            rf"{re.escape(label)}\s*:?\s*(.+?)(?=(?:\n|Market|Outcome|Probability|Date Range|$))",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(plain)
        if match:
            value = WS_RE.sub(" ", match.group(1)).strip(" .")
            if value:
                return value
    return None


def parse_metadata(body: str) -> ExportMetadata:
    plain = _strip_html(body)
    market = _label_value(body, ("Market",)) or "unknown"
    outcome = _label_value(body, ("Outcome",)) or "unknown"
    probability_range = _label_value(body, ("Probability Range", "Probability")) or "unknown"

    date_range_raw = _label_value(body, ("Date Range",)) or ""
    date_from = "unknown"
    date_to = "unknown"

    if date_range_raw:
        iso_pair = re.search(
            r"(\d{4}-\d{2}-\d{2})\s*(?:to|–|-|—)\s*(\d{4}-\d{2}-\d{2})",
            date_range_raw,
            re.IGNORECASE,
        )
        if iso_pair:
            date_from, date_to = iso_pair.group(1), iso_pair.group(2)
        else:
            dmy_pair = re.search(
                r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\s*(?:to|–|-|—)\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
                date_range_raw,
                re.IGNORECASE,
            )
            if dmy_pair:
                date_from, date_to = dmy_pair.group(1), dmy_pair.group(2)

    if date_from == "unknown":
        inline = re.search(
            r"Date Range\s*:?\s*(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})",
            plain,
            re.IGNORECASE,
        )
        if inline:
            date_from, date_to = inline.group(1), inline.group(2)
            date_range_raw = f"{date_from} to {date_to}"

    return ExportMetadata(
        market=market,
        outcome=outcome,
        probability_range=probability_range,
        date_from=date_from,
        date_to=date_to,
        date_range_raw=date_range_raw,
    )


def extract_csv_urls(body: str) -> list[str]:
    urls: list[str] = []
    for pattern in (CDN_URL_RE, HREF_CDN_RE):
        urls.extend(pattern.findall(body))
    cleaned: list[str] = []
    seen: set[str] = set()
    for url in urls:
        u = url.rstrip(".,;)")
        u = unquote(u)
        if CDN_HOST not in u.lower():
            continue
        if u in seen:
            continue
        seen.add(u)
        cleaned.append(u)
    return cleaned


def decode_message_body(payload: dict[str, Any]) -> str:
    parts: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime in ("text/plain", "text/html", ""):
            raw = base64.urlsafe_b64decode(data + "==")
            charset = "utf-8"
            for param in part.get("headers") or []:
                if (param.get("name") or "").lower() == "content-type":
                    charset_match = re.search(r"charset=([^\s;]+)", param.get("value", ""), re.I)
                    if charset_match:
                        charset = charset_match.group(1).strip("\"'")
            try:
                parts.append(raw.decode(charset, errors="replace"))
            except LookupError:
                parts.append(raw.decode("utf-8", errors="replace"))
        for child in part.get("parts") or []:
            walk(child)

    if payload.get("body", {}).get("data"):
        walk(payload)
    else:
        walk(payload)
    return "\n".join(parts)


def build_output_path(
    base_dir: Path,
    metadata: ExportMetadata,
    *,
    market_slug: str | None = None,
    outcome_slug: str | None = None,
) -> Path:
    date_folder = (
        f"{slugify(metadata.date_from)}_to_{slugify(metadata.date_to)}"
        if metadata.date_from != "unknown" and metadata.date_to != "unknown"
        else "unknown_date_range"
    )
    market = market_slug or slugify(metadata.market)
    outcome = outcome_slug or slugify(metadata.outcome)
    date_from = slugify(metadata.date_from)
    date_to = slugify(metadata.date_to)
    filename = f"{market}__{outcome}__{date_from}_to_{date_to}.csv"
    return base_dir / date_folder / market / filename


def resolve_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 1
    while True:
        candidate = parent / f"{stem}__dup{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def parse_email_export(
    *,
    email_id: str,
    received_at: str,
    body: str,
) -> EmailExport:
    metadata = parse_metadata(body)
    urls = extract_csv_urls(body)
    return EmailExport(
        email_id=email_id,
        received_at=received_at,
        metadata=metadata,
        csv_urls=urls,
        body_preview=_strip_html(body)[:500],
    )


def load_manifest(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in MANIFEST_COLUMNS})


def manifest_key(email_id: str, url: str) -> tuple[str, str]:
    return email_id, url


def already_downloaded(rows: list[dict[str, str]], email_id: str, url: str) -> bool:
    for row in rows:
        if row.get("email_id") == email_id and row.get("original_url") == url:
            if row.get("download_status") == "ok" and row.get("local_path"):
                lp = Path(row["local_path"])
                if lp.is_file() and lp.stat().st_size > 0:
                    return True
    return False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_csv(url: str, dest: Path, *, timeout: float = 120.0) -> tuple[int, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        content = response.content
        if not content.strip():
            raise ValueError("empty CSV response")
        dest.write_bytes(content)
    return len(content), sha256_bytes(content)


def process_exports(
    exports: list[EmailExport],
    *,
    output_dir: Path,
    manifest_path: Path,
    dry_run: bool = True,
) -> tuple[list[dict[str, str]], RunSummary]:
    summary = RunSummary(emails_found=len(exports), dry_run=dry_run)
    manifest_rows = load_manifest(manifest_path)
    existing_keys = {
        manifest_key(r.get("email_id", ""), r.get("original_url", ""))
        for r in manifest_rows
        if r.get("download_status") == "ok"
    }
    new_rows: list[dict[str, str]] = []

    for export in exports:
        if not export.csv_urls:
            new_rows.append(
                {
                    "email_id": export.email_id,
                    "received_at": export.received_at,
                    "market": export.metadata.market,
                    "outcome": export.metadata.outcome,
                    "probability_range": export.metadata.probability_range,
                    "date_from": export.metadata.date_from,
                    "date_to": export.metadata.date_to,
                    "original_url": "",
                    "local_path": "",
                    "file_size": "0",
                    "sha256": "",
                    "download_status": "no_link",
                    "error": "no oddalertscdn URL found in email body",
                }
            )
            summary.failed_links += 1
            continue

        for url in export.csv_urls:
            summary.links_found += 1
            key = manifest_key(export.email_id, url)
            if key in existing_keys or already_downloaded(manifest_rows, export.email_id, url):
                summary.skipped_links += 1
                continue

            dest = resolve_unique_path(build_output_path(output_dir, export.metadata))
            row = {
                "email_id": export.email_id,
                "received_at": export.received_at,
                "market": export.metadata.market,
                "outcome": export.metadata.outcome,
                "probability_range": export.metadata.probability_range,
                "date_from": export.metadata.date_from,
                "date_to": export.metadata.date_to,
                "original_url": url,
                "local_path": str(dest),
                "file_size": "0",
                "sha256": "",
                "download_status": "dry_run" if dry_run else "pending",
                "error": "",
            }

            if dry_run:
                row["download_status"] = "dry_run"
                new_rows.append(row)
                continue

            try:
                size, digest = download_csv(url, dest)
                row["file_size"] = str(size)
                row["sha256"] = digest
                row["download_status"] = "ok"
                summary.files_downloaded += 1
                summary.total_size_bytes += size
                existing_keys.add(key)
            except Exception as exc:
                row["download_status"] = "failed"
                row["error"] = str(exc)
                summary.failed_links += 1
                logger.exception("download failed for %s", url)

            new_rows.append(row)

    merged = manifest_rows + new_rows
    if not dry_run:
        write_manifest(manifest_path, merged)
    elif new_rows:
        write_manifest(manifest_path.with_suffix(".dry_run.csv"), merged)

    return merged, summary


def format_received_at(internal_date_ms: str | int | None, date_header: str | None) -> str:
    if internal_date_ms is not None:
        try:
            ts = int(internal_date_ms) / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except (TypeError, ValueError):
            pass
    if date_header:
        try:
            dt = parsedate_to_datetime(date_header)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def gmail_message_to_export(message: dict[str, Any]) -> EmailExport:
    payload = message.get("payload") or {}
    headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers") or []}
    body = decode_message_body(payload)
    return parse_email_export(
        email_id=message.get("id", ""),
        received_at=format_received_at(message.get("internalDate"), headers.get("date")),
        body=body,
    )


def build_gmail_service(credentials_path: Path, token_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Gmail dependencies missing. Install with: "
            "pip install -r requirements-oddalerts-gmail.txt"
        ) from exc

    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), [GMAIL_READONLY_SCOPE])

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.is_file():
                raise FileNotFoundError(
                    f"Gmail OAuth client secrets not found: {credentials_path}\n"
                    "Download OAuth desktop credentials JSON from Google Cloud Console "
                    "and save as credentials/gmail_oauth_client.json"
                )
            logger.info(
                "Gmail OAuth required — opening browser for read-only access. "
                "Sign in with the Gmail account that receives OddAlerts exports."
            )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                [GMAIL_READONLY_SCOPE],
            )
            creds = flow.run_local_server(port=0, open_browser=True)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def fetch_matching_exports(
    service,
    *,
    query: str = DEFAULT_SEARCH_QUERY,
    max_messages: int = 500,
) -> list[EmailExport]:
    exports: list[EmailExport] = []
    page_token: str | None = None

    while True:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token, maxResults=100)
            .execute()
        )
        for item in response.get("messages") or []:
            msg_id = item.get("id")
            if not msg_id:
                continue
            full = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            exports.append(gmail_message_to_export(full))
            if len(exports) >= max_messages:
                return exports
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return exports


def print_summary(summary: RunSummary) -> None:
    mode = "DRY RUN" if summary.dry_run else "DOWNLOAD"
    print(f"\n=== OddAlerts Gmail CSV Export ({mode}) ===")
    print(f"Emails found:      {summary.emails_found}")
    print(f"Links found:       {summary.links_found}")
    print(f"Files downloaded:  {summary.files_downloaded}")
    print(f"Failed links:      {summary.failed_links}")
    print(f"Skipped (exists):  {summary.skipped_links}")
    print(f"Total size:        {summary.total_size_bytes:,} bytes ({summary.total_size_bytes / 1024 / 1024:.2f} MB)")
