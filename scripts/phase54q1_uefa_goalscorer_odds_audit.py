#!/usr/bin/env python3
"""Phase 54Q-1 — UEFA goalscorer odds coverage audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.runner import run_phase54q1

    report = run_phase54q1()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "uefa_coverage_pct": (report.get("coverage") or {}).get("dataset_v3", {}).get("uefa_coverage_pct"),
                "wc_odds_lift": (report.get("wc_odds_lift") or {}).get("odds_lift_top3_blend_vs_ml"),
                "primary_limitation": (report.get("decision") or {}).get("primary_limitation"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
