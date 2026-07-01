#!/usr/bin/env python3
"""PHASE WDE-SHADOW-3 Part A — Shadow market inference (O/U2.5 + BTTS only, artifact only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.owner_daily.constants import DEFAULT_TIMEZONE
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly
from worldcup_predictor.research.wde_shadow_market_filters import apply_filters_to_payload
from worldcup_predictor.research.wde_shadow_market_inference import (
    DEFAULT_MODEL_DIR,
    run_shadow_market_predictions,
    write_predictions_artifact,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="WDE shadow market predictions dry-run")
    parser.add_argument("--date", default="today", help="Anchor date: today, tomorrow, or YYYY-MM-DD")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    anchor = resolve_target_date(args.date, args.timezone)
    conn = connect_readonly(get_settings().sqlite_path)
    try:
        payload = run_shadow_market_predictions(
            conn,
            date_arg=args.date,
            window_days=args.window_days,
            model_dir=model_dir,
            timezone=args.timezone,
        )
    finally:
        conn.close()

    payload = apply_filters_to_payload(payload)
    out_path = write_predictions_artifact(payload, anchor=anchor)
    print(json.dumps({"artifact": str(out_path), "scored_count": payload.get("scored_count")}, indent=2))
    print(f"Written: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
