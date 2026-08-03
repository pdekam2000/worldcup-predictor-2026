#!/usr/bin/env python3
"""Select next 15 strongest 1X2 candidates from upcoming predictions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.next_15_strongest_1x2.select import run_selection


def main() -> int:
    result = run_selection()
    print(
        json.dumps(
            {k: result.get(k) for k in ("status", "upcoming_n", "top15_n", "top15_priced_n", "source_artifact", "out_dir", "safety")},
            indent=2,
            default=str,
        )
    )
    for r in result.get("top15") or []:
        print(
            f"#{r['rank']} {r['date']} {r['match']} | WDE={r['wde_decision']} ECSE={r['ecse_direction']} "
            f"conf={r['wde_confidence']} class={r['classification']} score={r['research_score']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
