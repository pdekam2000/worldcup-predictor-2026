#!/usr/bin/env python3
"""Phase 54L — Goalscorer ML Shadow Engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_ml_shadow.runner import run_ml_shadow

    report = run_ml_shadow()
    print(json.dumps({
        "recommendation": report.recommendation,
        "baseline_comparison": report.baseline_comparison,
        "anytime_ensemble": next(
            (r.to_dict() for r in report.ranking if r.market == "anytime" and r.model == "ensemble"),
            {},
        ),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
