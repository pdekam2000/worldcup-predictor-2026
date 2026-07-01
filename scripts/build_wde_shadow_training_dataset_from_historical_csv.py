#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-1 Part B — Build WDE shadow training dataset from staging."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.wde_shadow_historical.dataset_builder import build_shadow_dataset
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build WDE shadow training dataset")
    parser.add_argument("--force", action="store_true", help="Build even if readiness gate warns")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    settings = get_settings()
    conn = connect_readonly(settings.sqlite_path)

    result = build_shadow_dataset(conn, force=args.force)
    conn.close()

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.row_count > 0 and not result.skipped_reason else 1


if __name__ == "__main__":
    raise SystemExit(main())
