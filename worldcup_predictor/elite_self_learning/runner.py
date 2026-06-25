"""Phase 58A — Elite Self Learning Engine runner."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.elite_self_learning.adaptive_weights import adaptive_weight_spec, recommend_weights
from worldcup_predictor.elite_self_learning.component_scoring import compute_rolling_scores, league_rollup
from worldcup_predictor.elite_self_learning.learning_store import (
    EliteLearningStore,
    build_calibration,
    build_component_health,
    build_league_health,
    build_market_health,
    build_patterns,
)
from worldcup_predictor.elite_self_learning.models import VALID_RECOMMENDATIONS
from worldcup_predictor.elite_self_learning.simulation import run_shadow_replay

ARTIFACT_DIR = Path("artifacts/phase58a_self_learning_engine")
REPORT_PATH = Path("PHASE_58A_SELF_LEARNING_ENGINE_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide_recommendation(
    evaluations: list[dict[str, Any]],
    component_health: dict[str, Any],
    weight_recs: list[Any],
) -> str:
    n = len(evaluations)
    if n < 100:
        return "NOT_RECOMMENDED"
    degraded = sum(1 for h in component_health.values() if h.get("status") == "degraded")
    shifts = sum(1 for r in weight_recs if r.direction != "hold")
    if n >= 500 and degraded <= 2 and shifts > 0:
        return "SELF_LEARNING_READY"
    if n >= 200:
        return "NEEDS_SHADOW"
    return "NEEDS_SHADOW"


def run_phase58a() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    spec = adaptive_weight_spec()
    (ARTIFACT_DIR / "adaptive_weight_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")

    evaluations = run_shadow_replay()
    store = EliteLearningStore()
    store.ensure_dirs()
    for ev in evaluations:
        store.append_evaluation(ev)

    scores = compute_rolling_scores(evaluations)
    scores.extend(league_rollup(scores))
    weight_recs = recommend_weights(scores)

    component_health = build_component_health(scores)
    market_health = build_market_health(evaluations)
    league_health = build_league_health(evaluations)
    calibration = build_calibration(evaluations)
    patterns = build_patterns(scores, weight_recs)

    store_paths = store.save_knowledge(
        patterns=patterns,
        component_health=component_health,
        market_health=market_health,
        league_health=league_health,
        calibration=calibration,
        weight_recommendations=[r.to_dict() for r in weight_recs],
    )

    (ARTIFACT_DIR / "rolling_component_scores.json").write_text(
        json.dumps([s.to_dict() for s in scores], indent=2), encoding="utf-8"
    )
    (ARTIFACT_DIR / "weight_recommendations.json").write_text(
        json.dumps([r.to_dict() for r in weight_recs], indent=2), encoding="utf-8"
    )
    (ARTIFACT_DIR / "replay_summary.json").write_text(
        json.dumps(
            {
                "fixtures_evaluated": len(evaluations),
                "fusion_correct": sum(1 for e in evaluations if e.get("fusion_correct")),
                "store_paths": store_paths,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    recommendation = decide_recommendation(evaluations, component_health, weight_recs)
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "NEEDS_SHADOW"

    decision = {
        "can_become_self_learning": recommendation != "NOT_RECOMMENDED",
        "components_to_adapt": [
            r.component_id for r in weight_recs if r.direction == "increase" and r.delta > 0
        ],
        "components_to_reduce": [
            r.component_id for r in weight_recs if r.direction == "decrease" and r.delta < 0
        ],
        "weight_evolution": "Slow shadow-only EMA (lr=0.02, max_delta=5%) with renormalization",
        "safeguards": [s["id"] for s in spec.get("safeguards", [])],
        "recommendation": recommendation,
    }
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    report = {
        "generated_at": _utc_now(),
        "phase": "58A",
        "fixtures_evaluated": len(evaluations),
        "component_scores": len(scores),
        "weight_recommendations": len(weight_recs),
        "decision": decision,
        "recommendation": recommendation,
        "store_paths": store_paths,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase58a_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    _write_markdown(report, spec, evaluations, scores, weight_recs, component_health, market_health, decision)
    return report


def _write_markdown(
    report: dict[str, Any],
    spec: dict[str, Any],
    evaluations: list[dict[str, Any]],
    scores: list[Any],
    weight_recs: list[Any],
    component_health: dict[str, Any],
    market_health: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    n = len(evaluations)
    correct = sum(1 for e in evaluations if e.get("fusion_correct"))
    acc = round(correct / n, 4) if n else 0

    lines = [
        "# PHASE 58A — Elite Self Learning Engine",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}",
        "**Mode:** Post-Match Learning → Component Evaluation → Adaptive Weighting",
        "**Status:** Complete — design + shadow replay",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Post-Match Evaluation",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Fixtures evaluated | {n} |",
        f"| Fusion accuracy (FGT) | {acc:.2%} |",
        f"| Store | `data/shadow/elite_learning_store/post_match_evaluations.jsonl` |",
        "",
        "Per market stored: `prediction`, `reality`, `outcome`, `confidence`, `tier`",
        "",
        "## Part B — Component Contributions",
        "",
        "| Component | Role in attribution |",
        "|-----------|---------------------|",
        "| lineup_intelligence | Starter gate / team pick proxy |",
        "| goalscorer_intelligence | Top scorer team direction |",
        "| market_behavior_intelligence | MBI prior direction |",
        "| odds_intelligence | Implied favorite |",
        "| egie_historical_baseline | Production EGIE proxy |",
        "| hybrid_confidence_engine | Tier calibration only |",
        "",
        "## Part C — Component Scoring",
        "",
        "Rolling windows: **100 / 500 / 1000** — by component, market, and league.",
        "",
        "### Top performers (window=100, global)",
        "",
        "| Component | Market | Help% | Hurt% | N |",
        "|-----------|--------|-------|-------|---|",
    ]

    top = sorted(
        [s for s in scores if s.window == 100 and s.league_id is None],
        key=lambda s: s.help_rate - s.hurt_rate,
        reverse=True,
    )[:8]
    for s in top:
        lines.append(f"| {s.component_id} | {s.market_id} | {s.help_rate:.2%} | {s.hurt_rate:.2%} | {s.n} |")

    lines.extend(
        [
            "",
            "## Part D — Adaptive Weighting",
            "",
            f"Learning rate: **{spec['config']['learning_rate']}** | Max delta: **{spec['config']['max_delta_per_cycle']}**",
            "",
            "### Shadow weight recommendations",
            "",
            "| Component | Market | Current | Recommended | Direction |",
            "|-----------|--------|---------|-------------|-----------|",
        ]
    )
    for r in weight_recs[:12]:
        if r.delta != 0 or r.direction != "hold":
            lines.append(
                f"| {r.component_id} | {r.market_id} | {r.current_weight} | {r.recommended_weight} | {r.direction} |"
            )

    lines.extend(["", "### Safeguards", ""])
    for s in spec.get("safeguards", []):
        lines.append(f"- **{s['id']}**: {s['description']}")

    lines.extend(
        [
            "",
            "## Part E — Knowledge Store (`elite_learning_store`)",
            "",
            "| File | Contents |",
            "|------|----------|",
            "| `post_match_evaluations.jsonl` | Per-fixture evaluation records |",
            "| `component_health.json` | Component help/hurt status |",
            "| `market_health.json` | Per-market accuracy + tier calibration |",
            "| `league_health.json` | League-level FGT accuracy |",
            "| `confidence_calibration.json` | Brier / ECE proxies |",
            "| `patterns.json` | Top outperformers / underperformers |",
            "| `adaptive_weight_recommendations.json` | Shadow weight deltas |",
            "",
            "## Part F — Decision Questions",
            "",
            f"1. **Can Elite become self-learning?** {decision.get('can_become_self_learning')}",
            f"2. **Which components should adapt?** {', '.join(decision.get('components_to_adapt') or []) or 'pending more shadow data'}",
            f"3. **How should weights evolve?** {decision.get('weight_evolution')}",
            f"4. **What safeguards prevent drift?** {len(decision.get('safeguards') or [])} gates (shadow-only, caps, min samples, league isolation)",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, or automatic model updates",
            "- Shadow recommendations only — never self-edit production",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
