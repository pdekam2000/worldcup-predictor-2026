#!/usr/bin/env python3
"""Phase 54G — Sportmonks Pressure Index discovery & coverage audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54g_pressure_discovery"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54G Pressure Index discovery")
    parser.add_argument("--max-calls", type=int, default=350)
    parser.add_argument("--samples-per-season", type=int, default=5)
    parser.add_argument("--no-optional-leagues", action="store_true")
    args = parser.parse_args()

    from worldcup_predictor.feature_store.pressure_discovery.discovery_engine import PressureDiscoveryEngine

    engine = PressureDiscoveryEngine(
        max_calls=args.max_calls,
        samples_per_season=args.samples_per_season,
        artifact_dir=ARTIFACT_DIR,
    )
    result = engine.run(include_optional_leagues=not args.no_optional_leagues)
    if result.get("status") == "error":
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result.get("summary", {}), indent=2, default=str))
    print(f"\nArtifacts: {ARTIFACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
