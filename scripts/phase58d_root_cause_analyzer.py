#!/usr/bin/env python3
"""Phase 58D — Root Cause Analyzer (shadow-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.root_cause.runner import run_phase58d  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 58D Root Cause Analyzer")
    parser.add_argument("--historical-limit", type=int, default=None, help="Cap historical EGIE replay rows")
    parser.add_argument("--force", action="store_true", help="Regenerate knowledge_records.jsonl")
    args = parser.parse_args()

    report = run_phase58d(historical_limit=args.historical_limit, force_store=args.force)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
