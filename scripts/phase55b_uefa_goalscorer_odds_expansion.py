#!/usr/bin/env python3
"""Phase 55B — UEFA goalscorer odds expansion."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_uefa_expansion.runner import run_phase55b

    report = run_phase55b()
    print(
        json.dumps(
            {
                "recommendation": report.get("recommendation"),
                "uefa_fixtures_with_odds": (report.get("after_meta") or {}).get("uefa_fixtures_with_odds"),
                "coverage_after": (report.get("revalidation") or {}).get("after", {}).get("odds_coverage_pct"),
                "uefa_top3_delta": (report.get("revalidation") or {}).get("delta", {}).get("uefa_top3_pp"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
