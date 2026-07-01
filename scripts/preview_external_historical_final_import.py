#!/usr/bin/env python3
"""Dry-run preview of external historical final import (no production writes)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.external_historical_crosswalk import (  # noqa: E402
    PREVIEW_PATH,
    build_final_import_preview,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    conn = connect(get_settings().sqlite_path)
    preview = build_final_import_preview(conn)
    conn.close()
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    print(f"Written: {PREVIEW_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
