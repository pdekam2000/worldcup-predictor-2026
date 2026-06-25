#!/usr/bin/env python3
"""Phase 55A — Market edge discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.market_edge.runner import run_phase55a

    report = run_phase55a()
    top3 = (report.get("rankings") or [])[:3]
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "target_market": (report.get("dev_hours_recommendation") or {}).get("target_market"),
                "top3_markets": [m.get("display_name") for m in top3],
                "top_scores": [m.get("market_edge_score") for m in top3],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
