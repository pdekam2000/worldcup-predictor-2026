#!/usr/bin/env python3
"""Run ECSE prematch tail-risk detector research (shadow only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ecse_prematch_tail_risk.runner import run_prematch_tail_risk_research


def main() -> int:
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    print(f"Starting SHA: {sha}")
    terminal = run_prematch_tail_risk_research(ROOT)
    print(json.dumps(terminal, indent=2))
    print(terminal.get("final_status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
