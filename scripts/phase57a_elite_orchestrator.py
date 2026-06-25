#!/usr/bin/env python3
"""Phase 57A — Elite Prediction Orchestrator design."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.elite_orchestrator.runner import run_phase57a


def main() -> int:
    report = run_phase57a()
    print(
        json.dumps(
            {
                "validated_components": report.get("validated_components"),
                "shadow_priority_top": (report.get("shadow_priority") or [{}])[0].get("market_id"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
