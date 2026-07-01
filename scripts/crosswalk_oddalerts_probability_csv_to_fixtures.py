#!/usr/bin/env python3
"""Crosswalk OddAlerts probability CSV rows to local fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_probability_market_mapper import (
    PROCESS_DATE,
    crosswalk_probability_rows,
)

OUT = Path(f"artifacts/oddalerts_probability_all_market_fixture_crosswalk_{PROCESS_DATE.replace('-', '')}.json")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    result = crosswalk_probability_rows(conn)
    conn.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in result if k != "rows"}, indent=2))
    print(f"Written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
