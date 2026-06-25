#!/usr/bin/env python3
"""Phase 58A — Elite Self Learning Engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.elite_self_learning.runner import run_phase58a


def main() -> int:
    report = run_phase58a()
    print(json.dumps({"recommendation": report.get("recommendation"), "fixtures": report.get("fixtures_evaluated")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
