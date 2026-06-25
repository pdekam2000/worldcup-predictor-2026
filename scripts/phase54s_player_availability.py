#!/usr/bin/env python3
"""Phase 54S — Player availability intelligence for goalscorer engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_intelligence.availability.runner import run_phase54s

    report = run_phase54s()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "availability_helps": (report.get("decision") or {}).get("availability_helps"),
                "uefa_top3": (report.get("uefa_analysis") or {})
                .get("overall", {})
                .get("player_lineup_availability_top3"),
                "closes_uefa_gap": (report.get("elite_path_test") or {}).get("closes_uefa_gap"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
