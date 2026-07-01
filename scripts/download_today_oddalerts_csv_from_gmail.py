#!/usr/bin/env python3
"""Download today's OddAlerts probability CSV exports from Gmail (owner/internal)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_today_gmail_downloader import (  # noqa: E402
    INBOX_DIR,
    PHASE,
    artifact_paths,
    build_lower_band_download_summary,
    build_lower_band_ecse_market_coverage,
    build_market_coverage,
    build_today_gmail_query,
    final_recommendation,
    lower_band_artifact_paths,
    lower_band_final_recommendation,
    run_today_download,
    summary_to_json,
)

DEFAULT_CREDENTIALS = ROOT / "credentials" / "gmail_oauth_client.json"
DEFAULT_TOKEN = ROOT / "data" / "imports" / "oddalerts_probability_exports" / ".gmail_token.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download today's OddAlerts CSV exports from Gmail")
    parser.add_argument("--date", default="2026-06-30", help="Process date YYYY-MM-DD (default: 2026-06-30)")
    parser.add_argument("--inbox-dir", type=Path, default=INBOX_DIR)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--token", type=Path, default=DEFAULT_TOKEN)
    parser.add_argument("--max-messages", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tag-ecse-complete", action="store_true", help="Tag summary records as ecse_complete coverage exports")
    parser.add_argument("--tag-ecse-lower-band", action="store_true", help="Tag/filter lower-band 0-50 exports for ECSE")
    parser.add_argument("--tag", default=None, help="Pipeline tag label (e.g. daily-owner-oddalerts)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    expected_query = build_today_gmail_query(args.date)
    logging.info("Gmail query: %s", expected_query)
    logging.info("Inbox: %s", args.inbox_dir.resolve())

    summary = run_today_download(
        process_date=args.date,
        inbox_dir=args.inbox_dir.resolve(),
        credentials_path=args.credentials.resolve(),
        token_path=args.token.resolve(),
        max_messages=args.max_messages,
        dry_run=args.dry_run,
    )

    if summary.gmail_query != expected_query:
        logging.error("Query mismatch — aborting artifact write")
        return 2

    coverage = build_market_coverage(summary)
    recommendation = final_recommendation(summary, coverage)

    if args.tag_ecse_lower_band:
        default_tag = "ecse_lower_band"
        coverage_phase = "ODDALERTS-LOWER-BAND-GMAIL"
    elif args.tag_ecse_complete:
        default_tag = "ecse_complete"
        coverage_phase = "ODDALERTS-CSV-COMPLETE-COVERAGE-1"
    else:
        default_tag = ""
        coverage_phase = PHASE

    payload = summary_to_json(summary, default_coverage_tag=default_tag)
    payload["coverage_phase"] = coverage_phase
    payload["final_recommendation"] = recommendation
    if args.tag:
        payload["pipeline_tag"] = args.tag

    summary_path, coverage_path = artifact_paths(args.date)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    coverage_payload = coverage
    coverage_payload["final_recommendation"] = recommendation
    coverage_path.write_text(json.dumps(coverage_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lb_recommendation = None
    if args.tag_ecse_lower_band:
        lb_summary = build_lower_band_download_summary(summary)
        lb_summary["final_recommendation"] = lower_band_final_recommendation(
            summary, build_lower_band_ecse_market_coverage(summary)
        )
        lb_coverage = build_lower_band_ecse_market_coverage(summary)
        lb_coverage["final_recommendation"] = lb_summary["final_recommendation"]
        lb_summary_path, lb_coverage_path = lower_band_artifact_paths(args.date)
        lb_summary_path.write_text(json.dumps(lb_summary, indent=2, ensure_ascii=False), encoding="utf-8")
        lb_coverage_path.write_text(json.dumps(lb_coverage, indent=2, ensure_ascii=False), encoding="utf-8")
        lb_recommendation = lb_summary["final_recommendation"]
        print(json.dumps({k: lb_summary[k] for k in lb_summary if k != "records"}, indent=2, ensure_ascii=False))
        print(f"Written: {lb_summary_path}")
        print(f"Written: {lb_coverage_path}")
        print(f"Lower-band recommendation: {lb_recommendation}")

    print(json.dumps({k: payload[k] for k in payload if k != "records"}, indent=2, ensure_ascii=False))
    print(f"Written: {summary_path}")
    print(f"Written: {coverage_path}")
    print(f"Recommendation: {recommendation}")

    if summary.emails_found == 0:
        return 3
    if recommendation == "TODAY_ODDALERTS_LINKS_EXPIRED":
        return 4
    if args.tag_ecse_lower_band and lb_recommendation == "DOWNLOAD_FAILED":
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
