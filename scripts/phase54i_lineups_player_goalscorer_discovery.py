#!/usr/bin/env python3
"""Phase 54I — lineups, player stats, goalscorer odds discovery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54i_lineups_player_goalscorer_discovery"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54I lineup/player/goalscorer discovery")
    parser.add_argument("--skip-api", action="store_true", help="Cache scan only (no live API)")
    parser.add_argument("--max-calls", type=int, default=35)
    args = parser.parse_args()

    from worldcup_predictor.intelligence.phase54i_discovery.discovery_engine import run_discovery

    print("Running Phase 54I discovery (cache-first)...")
    result = run_discovery(max_api_calls=args.max_calls, skip_api=args.skip_api)
    totals = (result.get("lineups_discovery") or {}).get("totals") or {}
    print(
        json.dumps(
            {
                "fixtures_scanned": totals.get("fixtures_scanned"),
                "with_starting_xi": totals.get("with_starting_xi"),
                "with_goalscorer_odds": totals.get("with_goalscorer_odds"),
                "recommendation": result.get("recommendation"),
                "api_calls": (result.get("api_probe") or {}).get("api_calls_used"),
            },
            indent=2,
        )
    )
    print(f"Artifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
