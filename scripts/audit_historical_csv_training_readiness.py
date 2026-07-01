#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-1 Part A — Audit historical CSV training readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly
from worldcup_predictor.research.wde_shadow_historical.readiness_audit import (
    audit_training_readiness,
    write_readiness_outputs,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit historical CSV WDE training readiness")
    parser.add_argument("--timeout", type=int, default=120, help="SQLite busy timeout seconds")
    args = parser.parse_args()

    settings = get_settings()
    conn = connect_readonly(settings.sqlite_path)

    result = audit_training_readiness(conn)
    write_readiness_outputs(result)
    conn.close()

    print(json.dumps({"readiness": result.readiness, "usable_rows": result.usable_rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
