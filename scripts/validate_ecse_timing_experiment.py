#!/usr/bin/env python3
"""Validator for ECSE timing experiment + ephemeral isolation."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "worldcup_predictor" / "research" / "ecse_timing_experiment"
EPH = ROOT / "worldcup_predictor" / "research" / "canonical_ephemeral"
SCRIPTS = [
    ROOT / "scripts" / "run_ecse_timing_experiment.py",
    ROOT / "scripts" / "evaluate_ecse_timing_experiment.py",
    ROOT / "scripts" / "report_ecse_timing_experiment.py",
]


def main() -> int:
    failures: list[str] = []
    for name in (
        "constants.py",
        "ddl.py",
        "db.py",
        "store.py",
        "compare.py",
        "stable_union.py",
        "evaluate.py",
        "capture.py",
        "discovery.py",
        "isolation.py",
        "windows.py",
        "stats.py",
        "report_builder.py",
    ):
        if not (PKG / name).is_file():
            failures.append(f"missing timing/{name}")

    for name in ("constants.py", "write_guard.py", "facade.py", "types.py", "__init__.py"):
        if not (EPH / name).is_file():
            failures.append(f"missing ephemeral/{name}")

    capture_src = (PKG / "capture.py").read_text(encoding="utf-8")
    if "run_ephemeral_canonical_prediction" not in capture_src:
        failures.append("capture.py not using ephemeral facade")
    if "enqueue_prediction_job" in capture_src:
        failures.append("capture.py still uses GPT Actions jobs")
    if "CANONICAL_RESEARCH_EPHEMERAL" not in (EPH / "constants.py").read_text(encoding="utf-8"):
        failures.append("missing EXECUTION_MODE constant")
    if "run_isolation_preflight" not in capture_src:
        failures.append("capture.py missing MID/LATE isolation preflight")
    if "EARLY_FREEZE_SIDE_EFFECT_CREATED" not in capture_src:
        failures.append("missing EARLY freeze side-effect annotation")

    worker_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "worker.py").read_text(encoding="utf-8")
    if "run_ephemeral_canonical_prediction" in worker_src:
        failures.append("worker must not expose ephemeral facade")

    schemas_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "schemas.py").read_text(encoding="utf-8")
    if "CANONICAL_RESEARCH_EPHEMERAL" in schemas_src or "ephemeral" in schemas_src.lower():
        failures.append("schemas must not expose ephemeral mode")

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
        failures.append("missing docs")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"- {f}")
        return 1
    print("PASS")
    print("ECSE_EPHEMERAL_ISOLATION_VALIDATOR_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
