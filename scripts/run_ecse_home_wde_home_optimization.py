#!/usr/bin/env python3
"""Run ECSE HOME ∧ WDE HOME forensic optimization (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ecse_home_wde_home_optimization.pipeline import run


def main() -> int:
    result = run()
    print(
        json.dumps(
            {
                k: result.get(k)
                for k in ("status", "decision", "decision_text", "base_n", "wins", "losses", "candidates_tested", "passing", "out_dir", "safety")
            },
            indent=2,
            default=str,
        )
    )
    final = result.get("final") or {}
    print("--- DECISION ---")
    print(final.get("decision"), final.get("decision_text"))
    print("why:", final.get("why"))
    if final.get("superior_rule"):
        print(json.dumps(final["superior_rule"], indent=2, default=str)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
