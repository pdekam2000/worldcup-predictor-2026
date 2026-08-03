#!/usr/bin/env python3
"""Run TRUE_FORWARD_472_COMPLETE_EVALUATION_AUDIT (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.true_forward_472_evaluation.pipeline import run_audit


def main() -> int:
    result = run_audit()
    print(json.dumps({k: result.get(k) for k in ("status", "status_note", "out_dir", "raw_tf_records", "unique_fixtures", "evaluated_unique_fixtures", "safety")}, indent=2, default=str))
    h = (result.get("reconciliation") or {}).get("headline") or {}
    print("--- HEADLINE ---")
    print(json.dumps(h, indent=2, default=str))
    return 0 if result.get("status") and "FAILED" not in str(result.get("status")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
