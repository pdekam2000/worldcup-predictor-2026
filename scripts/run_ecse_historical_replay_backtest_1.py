#!/usr/bin/env python3
"""ECSE-HISTORICAL-REPLAY-BACKTEST-1 runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_historical_replay.runner import run_backtest
import sqlite3


def main() -> int:
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    payload = run_backtest(conn)
    conn.close()
    print(json.dumps({"recommendation": payload.get("recommendation"), "replay_n": payload.get("replay_n")}, indent=2))
    print("ECSE_HISTORICAL_REPLAY_BACKTEST_1_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
