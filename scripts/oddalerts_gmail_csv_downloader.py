#!/usr/bin/env python3
"""
OddAlerts Gmail probability CSV export downloader.

Read-only Gmail OAuth (gmail.readonly). Downloads signed CSV links from
oddalertscdn.fra1.digitaloceanspaces.com before they expire (~24h).

Setup (one-time):
  1. Enable Gmail API in Google Cloud Console.
  2. Create OAuth desktop client → save as credentials/gmail_oauth_client.json
  3. pip install -r requirements-oddalerts-gmail.txt
  4. First run opens browser for consent (read-only).

Usage:
  python scripts/oddalerts_gmail_csv_downloader.py --dry-run
  python scripts/oddalerts_gmail_csv_downloader.py --download

Signed links expire quickly — run --download immediately after exports arrive.
Does not delete emails or touch the production database.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_gmail_exporter import (  # noqa: E402
    DEFAULT_SEARCH_QUERY,
    build_gmail_service,
    fetch_matching_exports,
    process_exports,
    print_summary,
)

DEFAULT_OUTPUT = ROOT / "data" / "imports" / "oddalerts_probability_exports"
DEFAULT_MANIFEST = DEFAULT_OUTPUT / "manifest.csv"
DEFAULT_CREDENTIALS = ROOT / "credentials" / "gmail_oauth_client.json"
DEFAULT_TOKEN = DEFAULT_OUTPUT / ".gmail_token.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download OddAlerts probability CSV exports from Gmail (read-only OAuth)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List emails/links and planned paths without downloading.",
    )
    mode.add_argument(
        "--download",
        action="store_true",
        help="Download all CSV files and update manifest.csv.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_SEARCH_QUERY,
        help=f'Gmail search query (default: "{DEFAULT_SEARCH_QUERY}")',
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output root (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest CSV path (default: <output-dir>/manifest.csv)",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS,
        help=f"OAuth client secrets JSON (default: {DEFAULT_CREDENTIALS})",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=DEFAULT_TOKEN,
        help=f"OAuth token cache (default: {DEFAULT_TOKEN})",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=500,
        help="Maximum emails to process (default: 500)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    output_dir = args.output_dir.resolve()
    manifest_path = (args.manifest or output_dir / "manifest.csv").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dry_run = args.dry_run
    if dry_run:
        logging.info("Dry-run mode — no files will be downloaded")
    else:
        logging.info("Download mode — fetching CSVs now (links expire ~24h)")

    logging.info("Gmail query: %s", args.query)
    logging.info("Output dir:  %s", output_dir)

    service = build_gmail_service(args.credentials.resolve(), args.token.resolve())
    exports = fetch_matching_exports(
        service,
        query=args.query,
        max_messages=args.max_messages,
    )

    for export in exports:
        logging.info(
            "Email %s | market=%r outcome=%r dates=%s..%s | links=%d",
            export.email_id,
            export.metadata.market,
            export.metadata.outcome,
            export.metadata.date_from,
            export.metadata.date_to,
            len(export.csv_urls),
        )
        for url in export.csv_urls:
            logging.info("  URL: %s", url[:120] + ("..." if len(url) > 120 else ""))

    _, summary = process_exports(
        exports,
        output_dir=output_dir,
        manifest_path=manifest_path,
        dry_run=dry_run,
    )
    print_summary(summary)

    if dry_run:
        print(f"\nDry-run manifest preview: {manifest_path.with_suffix('.dry_run.csv')}")
        return 0

    print(f"\nManifest: {manifest_path}")
    return 0 if summary.failed_links == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
