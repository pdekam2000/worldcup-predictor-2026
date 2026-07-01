#!/usr/bin/env python3
"""Build OddAlerts policy market matrix for high-confidence local fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.data_import.oddalerts_bookmaker_policy import (
    PROCESS_DATE,
    build_ecse_readiness_summary,
    build_policy_market_matrix,
)

OUT = Path(f"artifacts/oddalerts_policy_market_matrix_{PROCESS_DATE.replace('-', '')}.json")
ECSE_OUT = Path(f"artifacts/oddalerts_policy_ecse_readiness_{PROCESS_DATE.replace('-', '')}.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build OddAlerts policy market matrix")
    parser.add_argument("--allow-high-disagreement", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    conn = connect(get_settings().sqlite_path)
    matrix = build_policy_market_matrix(conn, allow_high_disagreement=args.allow_high_disagreement)
    ecse = build_ecse_readiness_summary(matrix)
    conn.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")
    ECSE_OUT.write_text(json.dumps(ecse, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"fixture_count": matrix["fixture_count"], "stats": matrix["stats"], "ecse": ecse["status_counts"]}, indent=2))
    print(f"Written: {OUT}")
    print(f"Written: {ECSE_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
