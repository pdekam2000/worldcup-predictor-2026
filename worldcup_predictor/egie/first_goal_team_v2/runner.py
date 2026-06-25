"""Phase 55C First Goal Team Engine V2 orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.first_goal_team_v2.dataset import build_dataset_v2
from worldcup_predictor.egie.first_goal_team_v2.evaluation import (
    decide_recommendation,
    feature_family_importance,
    run_backtest,
)
from worldcup_predictor.egie.first_goal_team_v2.models import FEATURE_GROUPS, VALID_RECOMMENDATIONS

ARTIFACT_DIR = Path("artifacts/phase55c_first_goal_team_v2")
REPORT_PATH = Path("PHASE_55C_FIRST_GOAL_TEAM_V2_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase55c() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    dataset, ds_meta = build_dataset_v2()
    dataset.to_parquet(ARTIFACT_DIR / "first_goal_team_dataset_v2.parquet", index=False)
    (ARTIFACT_DIR / "dataset_v2_summary.json").write_text(json.dumps(ds_meta, indent=2), encoding="utf-8")

    backtest = run_backtest(dataset)
    (ARTIFACT_DIR / "backtest_results.json").write_text(json.dumps(backtest, indent=2, default=str), encoding="utf-8")

    families = feature_family_importance(backtest)
    (ARTIFACT_DIR / "feature_family_importance.json").write_text(json.dumps(families, indent=2), encoding="utf-8")

    full = (backtest.get("groups") or {}).get("full_blend") or {}
    if full.get("tier_metrics"):
        (ARTIFACT_DIR / "confidence_tiers.json").write_text(
            json.dumps(full["tier_metrics"], indent=2), encoding="utf-8"
        )

    decision = decide_recommendation(backtest, families)
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    recommendation = decision.get("recommendation", "FIRST_GOAL_TEAM_NO_VALUE")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "FIRST_GOAL_TEAM_NO_VALUE"

    report = {
        "generated_at": _utc_now(),
        "phase": "55C",
        "dataset_v2": ds_meta,
        "backtest": backtest,
        "feature_families": families,
        "decision": decision,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase55c_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, backtest, families, decision, ds_meta)
    return report


def _write_markdown(
    report: dict[str, Any],
    backtest: dict[str, Any],
    families: dict[str, Any],
    decision: dict[str, Any],
    ds_meta: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    groups = backtest.get("groups") or {}
    tiers = (groups.get("full_blend") or {}).get("tier_metrics") or {}
    ranked = families.get("ranked") or []

    lines = [
        "# PHASE 55C — First Goal Team Engine V2",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Research → Shadow Engine → Validation  ",
        "**Status:** Complete — research only  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Dataset v2",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Rows | {ds_meta.get('rows')} |",
        f"| Fixtures | {ds_meta.get('fixtures')} |",
        f"| Goalscorer fixtures merged | {(ds_meta.get('sources') or {}).get('goalscorer_fixtures_merged')} |",
        f"| FTS odds rows | {(ds_meta.get('sources') or {}).get('fts_odds_non_null')} |",
        "",
        "Artifact: `artifacts/phase55c_first_goal_team_v2/first_goal_team_dataset_v2.parquet`",
        "",
        "## Part B — Feature group backtest (test split)",
        "",
        "| Group | Accuracy | Brier | ECE | Log-loss |",
        "|-------|----------|-------|-----|----------|",
    ]
    for name, m in groups.items():
        if m.get("status") != "ok":
            continue
        lines.append(
            f"| {name} | {m.get('accuracy')} | {m.get('brier')} | {m.get('ece')} | {m.get('log_loss')} |"
        )

    baselines = backtest.get("baselines") or {}
    lines.extend(
        [
            "",
            f"**54F-7 xG baseline reference:** {baselines.get('phase54f7_xg')}  ",
            f"**51H production reference:** {baselines.get('phase51h_production')}  ",
            f"**Goalscorer heuristic:** {(baselines.get('goalscorer_heuristic') or {}).get('accuracy')}",
            "",
            "## Part C — Calibration (full blend)",
            "",
            f"Brier: **{(groups.get('full_blend') or {}).get('brier')}**  ",
            f"ECE: **{(groups.get('full_blend') or {}).get('ece')}**",
            "",
            "## Part D — Confidence tiers (full blend)",
            "",
            "| Tier | N | Accuracy | Mean confidence |",
            "|------|---|----------|-----------------|",
        ]
    )
    for tier in ("A", "B", "C", "D"):
        t = tiers.get(tier) or {}
        lines.append(f"| {tier} | {t.get('n', 0)} | {t.get('accuracy', 'n/a')} | {t.get('mean_confidence', 'n/a')} |")

    lines.extend(
        [
            "",
            "## Part E — Decision questions",
            "",
            f"1. **Beat current baseline?** {decision.get('beats_54f7')} — best {decision.get('best_accuracy')} vs 54F-7 {baselines.get('phase54f7_xg')}",
            f"2. **Goalscorer signals help?** {float((families.get('family_deltas') or {}).get('goalscorer', 0)) > 0}",
            f"3. **Top feature family:** {ranked[0][0] if ranked else 'n/a'} ({ranked[0][1] if ranked else 0} pp)",
            f"4. **Stronger than goalscorer heuristic?** {decision.get('beats_goalscorer_heuristic')}",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, or live prediction changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
