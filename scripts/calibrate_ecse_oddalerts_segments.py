#!/usr/bin/env python3
"""Calibrate ECSE OddAlerts segment scoring from evaluated shadow outcomes."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.research.oddalerts_ecse_segment_calibration import (
    PROCESS_DATE,
    artifact_paths,
    build_calibration_analysis,
    build_feature_matrix,
)
from worldcup_predictor.research.oddalerts_ecse_shadow import DEFAULT_RUN_ID

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    paths = artifact_paths(PROCESS_DATE)
    db_path = get_db_path(get_settings().sqlite_path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120)
    conn.row_factory = sqlite3.Row

    matrix = build_feature_matrix(conn, shadow_run_id=DEFAULT_RUN_ID)
    calibration = build_calibration_analysis(matrix)
    conn.close()

    paths["feature_matrix"].write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["calibration"].write_text(json.dumps(calibration, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        json.dumps(
            {
                "records": matrix.get("record_count"),
                "evaluated": matrix.get("evaluated_count"),
                "buckets": len(calibration.get("buckets") or {}),
            },
            indent=2,
        )
    )
    print(f"Written: {paths['feature_matrix']}")
    print(f"Written: {paths['calibration']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
