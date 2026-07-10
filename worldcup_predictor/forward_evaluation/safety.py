"""Phase 7B Part M — Read-only model boundary guard."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORT_MARKERS = (
    "elite_self_learning",
    "weight_simulation",
    "adaptive_weights",
    "learning_store",
    "train",
    "retrain",
    "ScoringEngine",
    "ecse_rerank",
    "promotion_gate",
    "model_artifact",
    "threshold_updater",
)

FORBIDDEN_CALL_MARKERS = (
    "run_training",
    "optimize_weights",
    "promote_shadow",
    "update_calibration",
    "write_model_artifact",
    "retrain",
)


def scan_module_read_only_boundary(module_dir: Path) -> tuple[bool, list[str]]:
    violations: list[str] = []
    for path in module_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if f"import {marker}" in source or f"from worldcup_predictor.{marker}" in source:
                violations.append(f"{path.name}: forbidden import marker {marker}")
        for marker in FORBIDDEN_CALL_MARKERS:
            if f"{marker}(" in source:
                violations.append(f"{path.name}: forbidden call marker {marker}")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                if any(x in mod for x in ("elite_self_learning", "weight_simulation", "trl", "unsloth")):
                    violations.append(f"{path.name}: forbidden import from {mod}")
    return len(violations) == 0, violations


def confirm_read_only_boundary() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    ok, violations = scan_module_read_only_boundary(root)
    return {
        "status": "EVALUATION_READ_ONLY_MODEL_BOUNDARY_CONFIRMED" if ok else "BOUNDARY_VIOLATION",
        "violations": "; ".join(violations) if violations else "",
    }
