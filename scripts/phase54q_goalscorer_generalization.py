#!/usr/bin/env python3
"""Phase 54Q — Goalscorer intelligence stress test & generalization."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_intelligence.stress_runner import run_phase54q

    report = run_phase54q()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "fixtures": (report.get("dataset_v3") or {}).get("fixtures"),
                "overall_top3": (
                    ((report.get("overall_replay") or {}).get("markets") or {})
                    .get("anytime", {})
                    .get("composite_scorer", {})
                    .get("top3_hit")
                ),
                "elite_all_pass": (report.get("elite_test") or {}).get("all_pass"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
