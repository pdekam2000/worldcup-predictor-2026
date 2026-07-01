#!/usr/bin/env python3
"""Crosswalk external historical staging rows to local fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.external_historical_crosswalk import (  # noqa: E402
    CROSSWALK_PATH,
    build_fixture_crosswalk,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    conn = connect(get_settings().sqlite_path)
    summary = build_fixture_crosswalk(conn)
    conn.close()
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, indent=2, ensure_ascii=False))
    print(f"Written: {CROSSWALK_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
