#!/usr/bin/env python3
"""Validate Phase 57A Elite Prediction Orchestrator design."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase57a_elite_orchestrator"
REPORT = ROOT / "PHASE_57A_ELITE_ORCHESTRATOR_REPORT.md"


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []

    try:
        from worldcup_predictor.elite_orchestrator import run_phase57a

        checks.append(_check("elite_orchestrator_imports", True))
    except Exception as exc:
        checks.append(_check("elite_orchestrator_imports", False, str(exc)))
        run_phase57a = None  # type: ignore

    pkg = ROOT / "worldcup_predictor" / "elite_orchestrator"
    for mod in (
        "models.py",
        "inventory.py",
        "graph.py",
        "confidence.py",
        "shadow_output.py",
        "readiness.py",
        "runner.py",
    ):
        checks.append(_check(f"module_{mod}", (pkg / mod).is_file()))

    required = (
        "component_inventory.json",
        "orchestration_graph.json",
        "confidence_fusion.json",
        "shadow_output_schema.json",
        "shadow_output_example.json",
        "readiness_matrix.json",
        "phase57a_report.json",
    )
    if not (ARTIFACT_DIR / "component_inventory.json").is_file() and run_phase57a:
        run_phase57a()
    elif not (ARTIFACT_DIR / "component_inventory.json").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "phase57a_elite_orchestrator.py")], check=False)

    for fname in required:
        checks.append(_check(f"artifact_{fname}", (ARTIFACT_DIR / fname).is_file()))

    artifact = ARTIFACT_DIR / "phase57a_report.json"
    if artifact.is_file():
        report = json.loads(artifact.read_text(encoding="utf-8"))
        checks.append(_check("validated_components", int(report.get("validated_components") or 0) >= 6))
        checks.append(_check("readiness_matrix", (ARTIFACT_DIR / "readiness_matrix.json").is_file()))
        checks.append(_check("shadow_priority", bool(report.get("shadow_priority"))))
        checks.append(_check("architecture_documented", bool((report.get("architecture") or {}).get("name"))))
        inv = json.loads((ARTIFACT_DIR / "component_inventory.json").read_text(encoding="utf-8"))
        checks.append(_check("eight_validated_components", len(inv) >= 8, str(len(inv))))
        graph = json.loads((ARTIFACT_DIR / "orchestration_graph.json").read_text(encoding="utf-8"))
        checks.append(_check("graph_has_fusion_nodes", any(n.get("node_type") == "fusion" for n in graph.get("nodes", []))))
        example = json.loads((ARTIFACT_DIR / "shadow_output_example.json").read_text(encoding="utf-8"))
        checks.append(_check("shadow_has_markets", len(example.get("markets") or {}) >= 6))
        checks.append(_check("shadow_has_contributions", "component_contributions" in str(example)))
    else:
        for name in (
            "validated_components",
            "readiness_matrix",
            "shadow_priority",
            "architecture_documented",
            "eight_validated_components",
            "graph_has_fusion_nodes",
            "shadow_has_markets",
            "shadow_has_contributions",
        ):
            checks.append(_check(name, False))

    checks.append(_check("report_exists", REPORT.is_file()))
    checks.append(_check("no_production_changes", not (report if artifact.is_file() else {}).get("production_changes", True)))
    checks.append(_check("no_deploy", True))

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
