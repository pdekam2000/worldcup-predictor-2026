#!/usr/bin/env python3
"""PHASE EURO-B — Owner-only UEFA WDE/ECSE prediction generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.owner.euro_b_owner_predictions import run_owner_uefa_predictions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate owner-only UEFA WDE/ECSE predictions")
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=list(UEFA_CUP_KEYS),
        help="UEFA competition keys",
    )
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite existing owner predictions")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--wde-only", action="store_true")
    mode.add_argument("--ecse-only", action="store_true")
    mode.add_argument("--wde-and-ecse", action="store_true")
    parser.add_argument("--fetch-missing-odds", action="store_true", help="Reserved; not enabled in EURO-B")
    parser.add_argument("--max-api-calls", type=int, default=0)
    args = parser.parse_args()

    if args.wde_only:
        run_mode = "wde_only"
    elif args.ecse_only:
        run_mode = "ecse_only"
    else:
        run_mode = "wde_and_ecse"

    result = run_owner_uefa_predictions(
        competition_keys=args.competitions,
        days_ahead=args.days_ahead,
        mode=run_mode,
        dry_run=args.dry_run,
        force=args.force,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
