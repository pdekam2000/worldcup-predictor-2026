#!/usr/bin/env python3
"""Phase 54M — Goalscorer odds mapping & calibration layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from worldcup_predictor.egie.goalscorer_odds_mapping.runner import run_phase54m

    report = run_phase54m()
    print(json.dumps({
        "recommendation": report.get("recommendation"),
        "mapping_rate": (report.get("mapping_summary") or {}).get("mapping_rate"),
        "fixtures_with_odds": (report.get("audit") or {}).get("summary", {}).get("fixtures_with_goalscorer_odds"),
        "comparison_status": (report.get("comparison") or {}).get("status"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
