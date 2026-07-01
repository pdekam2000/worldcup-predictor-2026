#!/usr/bin/env python3
"""PHASE WDE-RETRAIN-SHADOW-1 — Run full shadow retrain prep pipeline (no training)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.wde_shadow_historical.constants import (
    DATASET_SUMMARY,
    READINESS_ARTIFACT,
)
from worldcup_predictor.research.wde_shadow_historical.prep_report import (
    derive_prep_recommendation,
    write_prep_report,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _run(script: str, *extra: str) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script), *extra]
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return int(proc.returncode)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run WDE shadow retrain prep (audit + dataset + validate)")
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    timeout_args = ["--timeout", str(args.timeout)]
    build_extra = [*timeout_args, *(["--force"] if args.force_build else [])]

    steps = [
        ("audit_historical_csv_training_readiness.py", timeout_args),
        ("build_wde_shadow_training_dataset_from_historical_csv.py", build_extra),
        ("validate_wde_shadow_training_dataset.py", timeout_args),
    ]

    results: dict[str, int] = {}
    for script, extra in steps:
        results[script] = _run(script, *extra)

    readiness = _load_json(READINESS_ARTIFACT)
    build = _load_json(DATASET_SUMMARY)
    validation_path = ROOT / "artifacts" / "wde_shadow_training_validation.json"
    validation = _load_json(validation_path) if validation_path.exists() else {}

    if not validation and READINESS_ARTIFACT.exists():
        recommendation = derive_prep_recommendation(readiness=readiness, build=build, validation=None)
        write_prep_report(recommendation=recommendation, readiness=readiness, build=build, validation={})

    recommendation = str(
        validation.get("recommendation")
        or derive_prep_recommendation(readiness=readiness, build=build, validation=validation or None)
    )

    summary = {
        "phase": "WDE-RETRAIN-SHADOW-1",
        "recommendation": recommendation,
        "readiness": readiness.get("readiness"),
        "staged_match_rows": readiness.get("staged_match_rows"),
        "usable_wde_1x2": (readiness.get("usable_rows") or {}).get("wde_1x2"),
        "dataset_row_count": build.get("row_count", 0),
        "dataset_skipped_reason": build.get("skipped_reason"),
        "validation_passed": validation.get("passed"),
        "steps": results,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if all(c == 0 for c in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
