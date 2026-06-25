#!/usr/bin/env python3
"""Phase 54R — Team context enrichment for goalscorer engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_intelligence.team_context.runner import run_phase54r

    report = run_phase54r()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "team_context_helps": (report.get("decision") or {}).get("team_context_helps"),
                "uefa_improvement_pp": (report.get("uefa_impact") or {}).get("overall", {}).get("improvement_pp"),
                "player_team_top3": (report.get("feature_groups") or {}).get("player_team", {}).get("top3_hit"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
