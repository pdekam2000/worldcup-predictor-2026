#!/usr/bin/env python3
"""Validate ECSE-HISTORICAL-REPLAY-BACKTEST-1 artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ART = ROOT / "artifacts" / "ecse_historical_replay_backtest_1"


def main() -> int:
    val_path = ART / "validation.json"
    if not val_path.is_file():
        print(json.dumps({"passed": False, "error": "run backtest first"}))
        return 1
    result = json.loads(val_path.read_text(encoding="utf-8"))
    print(json.dumps({"passed": result.get("passed"), "failed": result.get("failed")}, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
