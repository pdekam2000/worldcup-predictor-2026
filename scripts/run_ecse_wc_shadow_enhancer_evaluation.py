#!/usr/bin/env python3
"""PHASE ECSE-WC-1 — Run World Cup ECSE shadow enhancer evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_wc.wc_shadow_enhancer_evaluation import (
    WC_EVAL_JSONL,
    WC_EVAL_SUMMARY,
    run_wc_shadow_enhancer_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-WC-1 shadow enhancer evaluation")
    parser.add_argument("--competition", default="world_cup_2026")
    parser.add_argument("--json", action="store_true", dest="json_out")
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        result = run_wc_shadow_enhancer_evaluation(conn, competition_key=args.competition)
    finally:
        conn.close()

    payload = result.to_dict()
    if args.json_out:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(json.dumps(result.summary, indent=2, default=str))
        print(f"\nWrote {WC_EVAL_JSONL}")
        print(f"Wrote {WC_EVAL_SUMMARY}")

    return 0 if result.fixture_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
