#!/usr/bin/env python3
"""PHASE ODDALERTS-CSV-PLAYER-REF-1 — Crosswalk enrichment rows to local fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_enrichment_csv_importer import (
    CROSSWALK_PATH,
    build_enrichment_fixture_crosswalk,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="OddAlerts enrichment fixture crosswalk")
    parser.add_argument("--competition", default="world_cup_2026")
    parser.add_argument("--year", default="2026")
    args = parser.parse_args()

    conn = connect(get_settings().sqlite_path)
    summary = build_enrichment_fixture_crosswalk(
        conn,
        competition_key=args.competition,
        year_prefix=args.year,
        persist_links=True,
    )
    conn.commit()
    conn.close()

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Written: {CROSSWALK_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
