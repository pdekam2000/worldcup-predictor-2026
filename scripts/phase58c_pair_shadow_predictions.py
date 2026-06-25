#!/usr/bin/env python3
"""Phase 58C — Pair shadow predictions with post-match results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.elite_orchestrator.pairing import pair_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description="Pair elite shadow predictions with results")
    parser.add_argument("--force", action="store_true", help="Rewrite evaluations even if duplicate key exists")
    args = parser.parse_args()

    result = pair_predictions(force=args.force)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
