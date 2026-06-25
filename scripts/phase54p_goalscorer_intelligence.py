#!/usr/bin/env python3
"""Phase 54P — Goalscorer intelligence shadow layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_intelligence.runner import run_phase54p

    report = run_phase54p()
    anytime = ((report.get("replay") or {}).get("markets") or {}).get("anytime") or {}
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "fixtures": report.get("fixtures"),
                "composite_top3": (anytime.get("composite_scorer") or {}).get("top3_hit"),
                "blend_top3": (anytime.get("ml_odds_blend") or {}).get("top3_hit"),
                "value_picks": report.get("value_pick_count"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
