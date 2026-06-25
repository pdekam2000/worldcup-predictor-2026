#!/usr/bin/env python3
"""Phase 56A — Market Behavior Intelligence (MBI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.mbi.runner import run_phase56a


def main() -> int:
    report = run_phase56a()
    print(json.dumps({"recommendation": report.get("recommendation")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
