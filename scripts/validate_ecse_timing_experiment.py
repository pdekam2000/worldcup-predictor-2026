#!/usr/bin/env python3
"""Validator for ECSE timing experiment research package."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "worldcup_predictor" / "research" / "ecse_timing_experiment"
SCRIPTS = [
    ROOT / "scripts" / "run_ecse_timing_experiment.py",
    ROOT / "scripts" / "evaluate_ecse_timing_experiment.py",
    ROOT / "scripts" / "report_ecse_timing_experiment.py",
]


def main() -> int:
    failures: list[str] = []
    required = [
        "constants.py",
        "ddl.py",
        "db.py",
        "store.py",
        "compare.py",
        "stable_union.py",
        "evaluate.py",
        "capture.py",
        "discovery.py",
        "state_restore.py",
        "extract.py",
        "windows.py",
        "stats.py",
        "report_builder.py",
    ]
    for name in required:
        if not (PKG / name).is_file():
            failures.append(f"missing {name}")

    # Ensure capture hardcodes freeze_capture False
    capture_src = (PKG / "capture.py").read_text(encoding="utf-8")
    if "freeze_capture: False" not in capture_src and '"freeze_capture": False' not in capture_src:
        failures.append("capture.py missing freeze_capture=False")
    if "official_freeze\": False" not in capture_src and "'official_freeze': False" not in capture_src:
        failures.append("capture.py missing official_freeze=False")
    if "restore_prediction_state" not in capture_src:
        failures.append("capture.py missing restore")

    union_src = (PKG / "stable_union.py").read_text(encoding="utf-8")
    if "research_only" not in union_src or "final_decision_authority" not in union_src:
        failures.append("stable_union missing research-only labels")

    for sp in SCRIPTS:
        if not sp.is_file():
            failures.append(f"missing script {sp.name}")
            continue
        try:
            ast.parse(sp.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            failures.append(f"syntax {sp.name}: {exc}")

    docs = ROOT / "docs" / "research" / "ecse_timing_experiment.md"
    if not docs.is_file():
        failures.append("missing docs/research/ecse_timing_experiment.md")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"- {f}")
        return 1
    print("PASS")
    print("ECSE_TIMING_EXPERIMENT_VALIDATOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
