"""Phase 57A — Elite Prediction Orchestrator runner."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_orchestrator.confidence import confidence_fusion_spec
from worldcup_predictor.elite_orchestrator.graph import build_orchestration_graph
from worldcup_predictor.elite_orchestrator.inventory import (
    build_rejected_inventory,
    build_validated_inventory,
    inventory_summary,
)
from worldcup_predictor.elite_orchestrator.readiness import (
    build_readiness_matrix,
    readiness_summary,
    shadow_production_priority,
)
from worldcup_predictor.elite_orchestrator.shadow_output import (
    build_example_shadow_prediction,
    shadow_output_schema,
)

ARTIFACT_DIR = Path("artifacts/phase57a_elite_orchestrator")
REPORT_PATH = Path("PHASE_57A_ELITE_ORCHESTRATOR_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase57a() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    components = build_validated_inventory()
    rejected = build_rejected_inventory()
    inv_summary = inventory_summary(components)

    (ARTIFACT_DIR / "component_inventory.json").write_text(
        json.dumps([c.to_dict() for c in components], indent=2), encoding="utf-8"
    )
    (ARTIFACT_DIR / "rejected_components.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "inventory_summary.json").write_text(json.dumps(inv_summary, indent=2), encoding="utf-8")

    graph = build_orchestration_graph()
    (ARTIFACT_DIR / "orchestration_graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")

    conf_spec = confidence_fusion_spec()
    (ARTIFACT_DIR / "confidence_fusion.json").write_text(json.dumps(conf_spec, indent=2), encoding="utf-8")

    schema = shadow_output_schema()
    example = build_example_shadow_prediction()
    (ARTIFACT_DIR / "shadow_output_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    (ARTIFACT_DIR / "shadow_output_example.json").write_text(
        json.dumps(example.to_dict(), indent=2), encoding="utf-8"
    )

    matrix = build_readiness_matrix()
    priority = shadow_production_priority(matrix)
    rd_summary = readiness_summary(matrix)
    (ARTIFACT_DIR / "readiness_matrix.json").write_text(
        json.dumps([m.to_dict() for m in matrix], indent=2), encoding="utf-8"
    )
    (ARTIFACT_DIR / "shadow_priority.json").write_text(json.dumps(priority, indent=2), encoding="utf-8")

    production_ready = [c.component_id for c in components if c.readiness == "READY" and c.status == "validated"]
    research_only = [c.component_id for c in components if c.readiness in ("PARTIAL", "RESEARCH")]
    blocked = [c.component_id for c in components if c.readiness == "BLOCKED"]

    architecture = {
        "name": "Elite Prediction Engine",
        "mode": "shadow_only",
        "layers": [
            "input_adapters",
            "validated_component_runners",
            "market_fusion_nodes",
            "confidence_fusion",
            "elite_shadow_prediction",
        ],
        "excluded": list(rejected),
        "wiring": "Parallel component execution → per-market fusion → unified confidence → JSONL shadow store",
        "production_boundary": "No changes to PredictPipeline, WDE, or live API",
    }
    (ARTIFACT_DIR / "architecture.json").write_text(json.dumps(architecture, indent=2), encoding="utf-8")

    report = {
        "generated_at": _utc_now(),
        "phase": "57A",
        "inventory_summary": inv_summary,
        "validated_components": len(components),
        "rejected_components": len(rejected),
        "readiness_summary": rd_summary,
        "shadow_priority": priority,
        "production_ready_modules": production_ready,
        "research_only_modules": research_only,
        "architecture": architecture,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase57a_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    _write_markdown(report, components, rejected, graph, conf_spec, matrix, priority, architecture)
    return report


def _write_markdown(
    report: dict[str, Any],
    components: list[Any],
    rejected: list[dict[str, Any]],
    graph: dict[str, Any],
    conf_spec: dict[str, Any],
    matrix: list[Any],
    priority: list[dict[str, object]],
    architecture: dict[str, Any],
) -> None:
    lines = [
        "# PHASE 57A — Elite Prediction Orchestrator",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}",
        "**Mode:** Architecture → Shadow Integration → Ensemble Design",
        "**Status:** Complete — design only",
        "**API calls:** 0",
        "",
        "---",
        "",
        "## Part A — Component Inventory",
        "",
        f"**Validated components:** {len(components)} | **Rejected:** {len(rejected)}",
        "",
        "| Component | Confidence | Markets | Latency | Readiness |",
        "|-----------|------------|---------|---------|-----------|",
    ]
    for c in components:
        mkts = ", ".join(c.supported_markets[:3])
        if len(c.supported_markets) > 3:
            mkts += "…"
        lines.append(
            f"| {c.name} | {c.confidence} | {mkts} | {c.latency_ms}ms | {c.readiness} |"
        )

    lines.extend(["", "### Excluded (rejected research)", ""])
    for r in rejected:
        lines.append(f"- **{r['component_id']}** ({r['phase']}): {r['reason']}")

    lines.extend(
        [
            "",
            "Artifact: `artifacts/phase57a_elite_orchestrator/component_inventory.json`",
            "",
            "## Part B — Orchestration Graph",
            "",
            f"**Version:** `{graph.get('version')}`",
            f"**Nodes:** {len(graph.get('nodes', []))} | **Edges:** {len(graph.get('edges', []))}",
            "",
            "```mermaid",
            graph.get("mermaid", ""),
            "```",
            "",
            "**Execution order:** " + " → ".join(graph.get("execution_order", [])),
            "",
            "## Part C — Confidence Fusion",
            "",
            "| Signal | Weight | Role |",
            "|--------|--------|------|",
        ]
    )
    for sig, spec in (conf_spec.get("signals") or {}).items():
        lines.append(f"| {sig} | {spec.get('weight')} | {spec.get('description', '')[:60]} |")

    lines.extend(
        [
            "",
            "**Tier thresholds:** A≥0.72, B≥0.58, C≥0.42, D<0.42",
            "",
            "## Part D — Shadow Output Object",
            "",
            "Single internal object: `EliteShadowPrediction`",
            "",
            "Per market: `prediction`, `confidence`, `tier`, `evidence`, `reasoning`, `component_contributions`",
            "",
            "Example: `artifacts/phase57a_elite_orchestrator/shadow_output_example.json`",
            "",
            "## Part E — Readiness Matrix",
            "",
            "| Market | Readiness | Shadow | Production | Primary components |",
            "|--------|-----------|--------|------------|------------------|",
        ]
    )
    for m in matrix:
        comps = ", ".join(m.primary_components[:2])
        lines.append(
            f"| {m.market_id} | **{m.readiness}** | {m.shadow_ready} | {m.production_ready} | {comps} |"
        )

    lines.extend(["", "### Shadow production priority", ""])
    for p in priority[:6]:
        lines.append(f"{p['rank']}. **{p['market_id']}** ({p['readiness']}) — {p['notes']}")

    lines.extend(
        [
            "",
            "## Part F — Decision Questions",
            "",
            "### 1. Which modules are production-ready?",
            "",
        ]
    )
    for mod in report.get("production_ready_modules") or []:
        lines.append(f"- `{mod}`")
    lines.extend(["", "Baseline anchors (already in production, not replaced):", ""])
    lines.append("- `egie_historical_baseline`")
    lines.append("- `hybrid_confidence_engine`")

    lines.extend(["", "### 2. Which modules remain research only?", ""])
    for mod in report.get("research_only_modules") or []:
        lines.append(f"- `{mod}`")

    lines.extend(
        [
            "",
            "### 3. Which markets should enter shadow production first?",
            "",
        ]
    )
    for i, p in enumerate(priority[:3], start=1):
        lines.append(f"{i}. **{p['market_id']}** — {p['notes']}")

    lines.extend(
        [
            "",
            "### 4. Final architecture for Elite Prediction Engine",
            "",
            "```",
            "Inputs → Validated Components (parallel) → Market Fusion → Confidence Fusion → EliteShadowPrediction",
            "```",
            "",
            "| Layer | Responsibility |",
            "|-------|----------------|",
            "| Input adapters | Lineups, player store, odds, MBI priors, EGIE baseline |",
            "| Component runners | 8 validated modules only — no pressure/team-context/availability/xG blend |",
            "| Market fusion | Per-market weighted ensemble with explicit contributions |",
            "| Confidence fusion | Tier A–D from agreement + odds + MBI + DQ |",
            "| Shadow store | `data/shadow/elite_orchestrator_predictions.jsonl` |",
            "",
            "**Boundary:** Zero changes to `PredictPipeline`, WDE, live API, or EGIE scoring.",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, or API changes",
            "- Design and shadow schema only",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
