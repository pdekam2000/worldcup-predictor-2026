#!/usr/bin/env python3
"""Run PHASE ECSE-LIVE-1 internal snapshot + evaluation cycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.ecse_live.scheduler import run_ecse_live_cycle


def main() -> int:
    settings = get_settings()
    report = run_ecse_live_cycle(settings=settings)
    print(json.dumps(report, indent=2, default=str))
    out = Path("artifacts/ecse_live_1_latest_cycle.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0 if report.get("status") in {"ok", "disabled"} else 1


if __name__ == "__main__":
    sys.exit(main())
