#!/usr/bin/env python3
"""Run O/U 2.5 regime mining + ECSE direction filtering (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ou25_regime_mining.pipeline import run_mining


def main() -> int:
    result = run_mining()
    print(json.dumps({k: result.get(k) for k in ("status", "status_note", "out_dir", "headline", "safety")}, indent=2, default=str))
    return 0 if result.get("status") and "FAILED" not in str(result.get("status")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
