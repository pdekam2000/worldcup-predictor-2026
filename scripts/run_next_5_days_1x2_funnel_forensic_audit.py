#!/usr/bin/env python3
"""Run NEXT_5_DAYS_1X2_SELECTION_FUNNEL_FORENSIC_AUDIT (research-only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.next_5_days_1x2_funnel_forensic import STATUS, run_audit


def main() -> int:
    validation = run_audit()
    print(STATUS)
    print("artifact_dir", validation.get("artifact_dir"))
    print("recommendation", validation.get("recommendation"))
    print("baseline_reproduced", validation.get("baseline_reproduced"))
    print("policy_counts", validation.get("policy_counts"))
    print("NOT DEPLOYED")
    print("CANONICAL UNCHANGED")
    print("FREEZES UNCHANGED")
    return 0 if validation.get("baseline_reproduced") else 1


if __name__ == "__main__":
    raise SystemExit(main())
