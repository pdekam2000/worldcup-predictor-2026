#!/usr/bin/env python3
"""Runtime read-only model boundary check for automation path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.safety import confirm_read_only_boundary

FORBIDDEN_MODULES = (
    "worldcup_predictor.learning",
    "worldcup_predictor.elite_self_learning",
    "worldcup_predictor.research.weight_simulation",
)


def main() -> int:
    static = confirm_read_only_boundary()
    import_checks = []
    for mod in FORBIDDEN_MODULES:
        try:
            __import__(mod)
            import_checks.append({"module": mod, "importable": True})
        except ImportError:
            import_checks.append({"module": mod, "importable": False})

    # Orchestrator must not import training paths
    orch_src = (ROOT / "worldcup_predictor/forward_evaluation/orchestrator.py").read_text(encoding="utf-8")
    runner_src = (ROOT / "worldcup_predictor/forward_evaluation/runner.py").read_text(encoding="utf-8")
    combined = orch_src + runner_src
    forbidden_calls = [
        "run_training",
        "optimize_weights",
        "promote_shadow",
        "update_calibration",
        "retrain(",
    ]
    violations = [c for c in forbidden_calls if c in combined]

    ok = static["status"] == "EVALUATION_READ_ONLY_MODEL_BOUNDARY_CONFIRMED" and not violations
    print(
        json.dumps(
            {
                "status": "EVALUATION_AUTOMATION_READ_ONLY_BOUNDARY_CONFIRMED" if ok else "BOUNDARY_FAIL",
                "static_scan": static,
                "orchestrator_forbidden_calls": violations,
                "training_modules_importable": import_checks,
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
