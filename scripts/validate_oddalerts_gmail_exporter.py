#!/usr/bin/env python3
"""Offline validation for OddAlerts Gmail email parsing (no API calls)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.data_import.oddalerts_gmail_exporter import (  # noqa: E402
    build_output_path,
    extract_csv_urls,
    parse_email_export,
    parse_metadata,
    slugify,
)

SAMPLE_HTML = """
<html><body>
<p>Your Probability Export is Ready</p>
<p><strong>Market:</strong> Over/Under 2.5 Goals</p>
<p><strong>Outcome:</strong> Over 2.5</p>
<p><strong>Probability Range:</strong> 60% - 80%</p>
<p><strong>Date Range:</strong> 2024-08-01 to 2025-05-31</p>
<p><a href="https://oddalertscdn.fra1.digitaloceanspaces.com/exports/prob_abc123.csv?X-Amz-Signature=xyz">Download CSV</a></p>
</body></html>
"""


def main() -> int:
    meta = parse_metadata(SAMPLE_HTML)
    assert meta.market == "Over/Under 2.5 Goals", meta.market
    assert meta.outcome == "Over 2.5", meta.outcome
    assert meta.probability_range == "60% - 80%", meta.probability_range
    assert meta.date_from == "2024-08-01", meta.date_from
    assert meta.date_to == "2025-05-31", meta.date_to

    urls = extract_csv_urls(SAMPLE_HTML)
    assert len(urls) == 1
    assert urls[0].startswith("https://oddalertscdn.fra1.digitaloceanspaces.com/")

    export = parse_email_export(email_id="test1", received_at="2026-06-27 12:00:00 UTC", body=SAMPLE_HTML)
    assert len(export.csv_urls) == 1

    out = build_output_path(Path("data/imports/oddalerts_probability_exports"), meta)
    assert "2024_08_01_to_2025_05_31" in str(out).replace("-", "_") or "2024-08-01" in str(out)
    assert slugify("Over/Under 2.5 Goals") == "over_under_2_5_goals"

    print("validate_oddalerts_gmail_exporter: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
