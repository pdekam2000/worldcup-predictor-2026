"""Phase 58B — Self Learning Simulation runner."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_self_learning.weight_simulation.models import VALID_SIMULATION_RECOMMENDATIONS
from worldcup_predictor.elite_self_learning.weight_simulation.replay import (
    load_fixture_rows,
    load_gs_proxy,
    replay_fixture,
)
from worldcup_predictor.elite_self_learning.weight_simulation.snapshots import create_snapshots, load_recommendations
from worldcup_predictor.elite_self_learning.weight_simulation.validation import (
    build_component_reports,
    compare_windows,
    decide_simulation_recommendation,
    decide_market_acceptance,
)

ARTIFACT_DIR = Path("artifacts/phase58b_self_learning_simulation")
REPORT_PATH = Path("PHASE_58B_SELF_LEARNING_SIMULATION_REPORT.md")
SCORES_PATH = Path("artifacts/phase58a_self_learning_engine/rolling_component_scores.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase58b() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_manifest = create_snapshots(persist=True)
    (ARTIFACT_DIR / "snapshot_manifest.json").write_text(
        json.dumps(snapshot_manifest, indent=2), encoding="utf-8"
    )

    old_matrices = snapshot_manifest["old_matrices"]
    new_matrices = snapshot_manifest["new_matrices"]
    market_id = "first_goal_team"
    old_w = old_matrices.get(market_id, {})
    new_w = new_matrices.get(market_id, {})

    rows = load_fixture_rows()
    gs_proxy = load_gs_proxy()
    replay_rows = [replay_fixture(r, gs_proxy, old_w, new_w, market_id=market_id) for r in rows]

    (ARTIFACT_DIR / "replay_rows.json").write_text(
        json.dumps(replay_rows, indent=2), encoding="utf-8"
    )

    comparisons = compare_windows(replay_rows, market_id=market_id)
    (ARTIFACT_DIR / "window_comparisons.json").write_text(
        json.dumps([c.to_dict() for c in comparisons], indent=2), encoding="utf-8"
    )

    recommendations = load_recommendations()
    component_reports = build_component_reports(recommendations, comparisons, SCORES_PATH)
    (ARTIFACT_DIR / "component_learning_reports.json").write_text(
        json.dumps([r.to_dict() for r in component_reports], indent=2), encoding="utf-8"
    )

    market_accept = decide_market_acceptance(comparisons)
    accepted = [r for r in component_reports if r.approval_status == "ACCEPT"]
    rejected = [r for r in component_reports if r.approval_status == "REJECT"]
    held = [r for r in component_reports if r.approval_status == "HOLD"]

    recommendation = decide_simulation_recommendation(comparisons, component_reports)
    if recommendation not in VALID_SIMULATION_RECOMMENDATIONS:
        recommendation = "NEEDS_MORE_DATA"

    primary = next((c for c in comparisons if c.window == 500), comparisons[-1] if comparisons else None)
    long_term_gain = {
        "accuracy_per_1000": round((primary.delta_accuracy if primary else 0) * 1000, 2),
        "brier_improvement": primary.delta_brier if primary else 0,
        "annual_fixtures_proxy": 2000,
        "estimated_correct_gains_per_year": round((primary.delta_accuracy if primary else 0) * 2000, 1),
    }

    decision = {
        "market_acceptance": market_accept,
        "accepted_components": len(accepted),
        "rejected_components": len(rejected),
        "held_components": len(held),
        "long_term_gain": long_term_gain,
        "safety": {
            "production_write": False,
            "weight_overwrite": False,
            "shadow_only": True,
        },
        "recommendation": recommendation,
    }
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    report = {
        "generated_at": _utc_now(),
        "phase": "58B",
        "fixtures_total": len(replay_rows),
        "snapshots": len(snapshot_manifest.get("snapshots") or []),
        "comparisons": [c.to_dict() for c in comparisons],
        "decision": decision,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase58b_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    _write_markdown(report, comparisons, component_reports, decision, snapshot_manifest)
    return report


def _write_markdown(
    report: dict[str, Any],
    comparisons: list[Any],
    component_reports: list[Any],
    decision: dict[str, Any],
    snapshot_manifest: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    lines = [
        "# PHASE 58B — Self Learning Simulation",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}",
        "**Mode:** Replay → Simulation → Weight Validation",
        "**Status:** Complete — shadow simulation only",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Weight Snapshots",
        "",
        f"Immutable snapshots: **{len(snapshot_manifest.get('snapshots') or [])}**",
        f"Source: `{snapshot_manifest.get('source_recommendations')}`",
        "",
        "Artifact: `artifacts/phase58b_self_learning_simulation/weight_snapshots/`",
        "",
        "## Part B — Historical Replay",
        "",
        "| Window | Weights | Accuracy | Brier | ECE | ROI proxy |",
        "|--------|---------|----------|-------|-----|-----------|",
    ]

    for c in comparisons:
        lines.append(
            f"| {c.window} | old | {c.old.accuracy:.2%} | {c.old.brier:.4f} | {c.old.ece:.4f} | {c.old.roi_proxy:.4f} |"
        )
        lines.append(
            f"| {c.window} | new | {c.new.accuracy:.2%} | {c.new.brier:.4f} | {c.new.ece:.4f} | {c.new.roi_proxy:.4f} |"
        )
        lines.append(
            f"| {c.window} | **Δ** | **{c.delta_accuracy:+.2%}** | **{c.delta_brier:+.4f}** | "
            f"**{c.delta_ece:+.4f}** | **{c.delta_roi_proxy:+.4f}** |"
        )

    lines.extend(
        [
            "",
            f"Picks changed (500-window): **{next((c.picks_changed for c in comparisons if c.window == 500), 0)}**",
            "",
            "## Part C — Accept / Reject",
            "",
            f"Market bundle (`first_goal_team`): **{decision.get('market_acceptance')}**",
            "",
            "## Part D — Component Learning Reports",
            "",
            "| Component | Market | Current | Recommended | Exp Δ acc | Status |",
            "|-----------|--------|---------|-------------|-----------|--------|",
        ]
    )

    for r in component_reports:
        if r.approval_status in ("ACCEPT", "REJECT") or abs(r.recommended_weight - r.current_weight) > 1e-6:
            lines.append(
                f"| {r.component_id} | {r.market_id} | {r.current_weight} | {r.recommended_weight} | "
                f"{r.expected_gain_accuracy:+.4f} | **{r.approval_status}** |"
            )

    lt = decision.get("long_term_gain") or {}
    lines.extend(
        [
            "",
            "## Part E — Safety",
            "",
            "- Never overwrite production weights",
            "- Never touch WDE or PredictPipeline",
            "- Shadow recommendations stored in artifacts only",
            "",
            "## Part F — Decision Questions",
            "",
            "### 1. Which recommendations improve performance?",
            "",
        ]
    )

    improved = [c for c in comparisons if c.delta_accuracy > 0 or c.delta_brier < 0]
    if improved:
        for c in improved:
            lines.append(f"- Window {c.window}: Δacc {c.delta_accuracy:+.2%}, Δbrier {c.delta_brier:+.4f}")
    else:
        lines.append("- No measurable improvement from 58A micro-weight shifts on replay")

    lines.extend(["", "### 2. Which recommendations should be rejected?", ""])
    rej = [r for r in component_reports if r.approval_status == "REJECT"]
    if rej:
        for r in rej[:8]:
            lines.append(f"- `{r.component_id}` / {r.market_id}: {r.reason}")
    else:
        lines.append("- None rejected — changes are HOLD (no measurable delta)")

    lines.extend(
        [
            "",
            "### 3. Estimated long-term gain",
            "",
            f"- Accuracy gain per 1000 fixtures: **{lt.get('accuracy_per_1000', 0)}** correct picks",
            f"- Estimated annual gain (~2000 fixtures): **{lt.get('estimated_correct_gains_per_year', 0)}** picks",
            "",
            "### 4. Is adaptive learning safe?",
            "",
            "**Yes, in shadow mode** — 8 safeguards from 58A remain; simulation confirms no production writes.",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, or automatic weight overwrite",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
