#!/usr/bin/env python3
"""Build ECSE complete-coverage readiness comparison artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_csv_request import (
    READINESS_PATH,
    write_coverage_readiness_artifact,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    conn = connect(get_settings().sqlite_path)
    payload = write_coverage_readiness_artifact(conn)
    conn.close()
    print(json.dumps(payload.get("comparison", {}), indent=2, ensure_ascii=False))
    print(f"Written: {READINESS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
