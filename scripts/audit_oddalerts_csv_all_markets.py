#!/usr/bin/env python3
"""PHASE ODDALERTS-CSV-MARKET-MAPPING-ALL — audit + import all probability CSV markets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_probability_market_mapper import (
    PROCESS_DATE,
    audit_probability_csvs,
    build_bookmaker_coverage,
    build_ecse_readiness_dryrun,
    discover_probability_csv_files,
    import_probability_rows,
)

AUDIT_OUT = Path(f"artifacts/oddalerts_all_markets_audit_{PROCESS_DATE.replace('-', '')}.json")
BOOKMAKER_OUT = Path(f"artifacts/oddalerts_bookmaker_coverage_{PROCESS_DATE.replace('-', '')}.json")
ECSE_OUT = Path(f"artifacts/oddalerts_probability_ecse_readiness_dryrun_{PROCESS_DATE.replace('-', '')}.json")
IMPORT_OUT = Path(f"artifacts/oddalerts_probability_market_import_{PROCESS_DATE.replace('-', '')}.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and import all OddAlerts probability CSV markets")
    parser.add_argument("--date", default=PROCESS_DATE)
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--truncate", action="store_true", help="Clear probability market rows before import")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    files = discover_probability_csv_files(conn)
    audit = audit_probability_csvs(files)
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    import_stats = {"skipped": True}
    if not args.skip_import:
        if args.truncate:
            conn.execute("DELETE FROM oddalerts_probability_market_rows")
            conn.commit()
        import_stats = import_probability_rows(conn, files)
        IMPORT_OUT.write_text(json.dumps(import_stats, indent=2, ensure_ascii=False), encoding="utf-8")
        bookmaker = build_bookmaker_coverage(conn)
        BOOKMAKER_OUT.write_text(json.dumps(bookmaker, indent=2, ensure_ascii=False), encoding="utf-8")
        ecse = build_ecse_readiness_dryrun(conn)
        ECSE_OUT.write_text(json.dumps(ecse, indent=2, ensure_ascii=False), encoding="utf-8")

    conn.close()

    print(json.dumps({"audit": {k: audit[k] for k in audit if k != "files"}, "import": import_stats}, indent=2))
    print(f"Written: {AUDIT_OUT}")
    if not args.skip_import:
        print(f"Written: {IMPORT_OUT}")
        print(f"Written: {BOOKMAKER_OUT}")
        print(f"Written: {ECSE_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
