#!/usr/bin/env python3
"""Run EESO shadow research — formalized Last-8 evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.eeso.runner import run_eeso_shadow_research


def main() -> int:
    starting_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    print(f"Starting SHA: {starting_sha}")

    terminal = run_eeso_shadow_research(ROOT)

    print(json.dumps(terminal, indent=2))
    print(terminal.get("final_status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
