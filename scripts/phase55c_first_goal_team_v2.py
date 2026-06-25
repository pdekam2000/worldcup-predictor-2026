#!/usr/bin/env python3
"""Phase 55C — First Goal Team Engine V2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.first_goal_team_v2.runner import run_phase55c

    report = run_phase55c()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "best_group": (report.get("decision") or {}).get("best_group"),
                "best_accuracy": (report.get("decision") or {}).get("best_accuracy"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
