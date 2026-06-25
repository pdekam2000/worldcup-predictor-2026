"""Phase 54R team context enrichment orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_intelligence.team_context.dataset_v4 import build_dataset_v4
from worldcup_predictor.egie.goalscorer_intelligence.team_context.evaluation import (
    decide_recommendation,
    elite_recheck,
    evaluate_feature_groups,
    team_feature_importance,
    uefa_league_impact,
)
from worldcup_predictor.egie.goalscorer_intelligence.team_context.models import (
    BASELINE_54Q_OVERALL_TOP3,
    BASELINE_54Q_UEFA_TOP3,
    VALID_RECOMMENDATIONS,
)

ARTIFACT_DIR = Path("artifacts/phase54r_team_context_goalscorer")
REPORT_PATH = Path("PHASE_54R_TEAM_CONTEXT_GOALSCORER_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase54r() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_v4, ds_meta = build_dataset_v4()
    dataset_v4.to_parquet(ARTIFACT_DIR / "goalscorer_dataset_v4.parquet", index=False)
    (ARTIFACT_DIR / "dataset_v4_summary.json").write_text(json.dumps(ds_meta, indent=2), encoding="utf-8")

    group_results = evaluate_feature_groups(dataset_v4)
    (ARTIFACT_DIR / "feature_group_results.json").write_text(json.dumps(group_results, indent=2), encoding="utf-8")

    feat_imp = team_feature_importance(dataset_v4)
    (ARTIFACT_DIR / "team_feature_importance.json").write_text(json.dumps(feat_imp, indent=2), encoding="utf-8")

    uefa_impact = uefa_league_impact(dataset_v4, group_results)
    (ARTIFACT_DIR / "uefa_league_impact.json").write_text(json.dumps(uefa_impact, indent=2), encoding="utf-8")

    elite = elite_recheck(uefa_impact, group_results)
    (ARTIFACT_DIR / "elite_recheck.json").write_text(json.dumps(elite, indent=2), encoding="utf-8")

    decision = decide_recommendation(group_results, feat_imp, uefa_impact, elite)
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    recommendation = decision.get("recommendation", "GOALSCORER_HIGH_VALUE")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "GOALSCORER_HIGH_VALUE"

    report = {
        "generated_at": _utc_now(),
        "phase": "54R",
        "dataset_v4": ds_meta,
        "feature_groups": group_results,
        "team_feature_importance": feat_imp,
        "uefa_impact": uefa_impact,
        "elite_recheck": elite,
        "decision": decision,
        "recommendation": recommendation,
        "baseline_54q": {
            "uefa_top3": BASELINE_54Q_UEFA_TOP3,
            "overall_top3": BASELINE_54Q_OVERALL_TOP3,
        },
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase54r_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, group_results, feat_imp, uefa_impact, elite, decision, ds_meta)
    return report


def _write_markdown(
    report: dict[str, Any],
    groups: dict[str, Any],
    feat_imp: dict[str, Any],
    uefa: dict[str, Any],
    elite: dict[str, Any],
    decision: dict[str, Any],
    ds_meta: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    lines = [
        "# PHASE 54R — Team Context Enrichment for Goalscorer Engine",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Research → Feature Expansion → Revalidation  ",
        "**Status:** Complete — research only  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Team context features",
        "",
        f"Built **{len(ds_meta.get('team_context_columns', []))}** team-level features joined to player rows.",
        "",
        "| Feature | Non-zero rows |",
        "|---------|---------------|",
    ]
    for feat, cnt in (ds_meta.get("non_zero_coverage") or {}).items():
        lines.append(f"| {feat} | {cnt:,} |")

    lines.extend(
        [
            "",
            "Artifact: `artifacts/phase54r_team_context_goalscorer/goalscorer_dataset_v4.parquet`",
            "",
            "## Part B — Dataset v4",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Rows | {ds_meta.get('rows'):,} |",
            f"| Fixtures | {ds_meta.get('fixtures')} |",
            "",
            "## Part C — Feature group test (test split)",
            "",
            "| Group | Top-1 | Top-3 | Top-5 | MRR |",
            "|-------|-------|-------|-------|-----|",
        ]
    )
    for name, m in groups.items():
        lines.append(
            f"| {name} | {m.get('top1_hit')} | {m.get('top3_hit')} | {m.get('top5_hit')} | {m.get('mrr')} |"
        )

    lines.extend(
        [
            "",
            "## Part D — Team feature importance",
            "",
            f"Baseline player+team top-3: **{feat_imp.get('baseline_top3')}**",
            "",
            "| Feature | Top-3 drop when removed | Verdict |",
            "|---------|-------------------------|---------|",
        ]
    )
    for feat, drop in feat_imp.get("ranked") or []:
        verdict = (feat_imp.get("verdicts") or {}).get(feat, "neutral")
        lines.append(f"| {feat} | {drop:+.4f} | {verdict} |")

    lines.extend(
        [
            "",
            f"**Positive:** {', '.join(feat_imp.get('positive') or []) or '—'}  ",
            f"**Neutral:** {len(feat_imp.get('neutral') or [])} features  ",
            f"**Harmful:** {', '.join(feat_imp.get('harmful') or []) or '—'}",
            "",
            "## Part E — UEFA impact (test split)",
            "",
            "| League | Lineup Top-3 | Team Top-3 | Δ pp |",
            "|--------|--------------|------------|------|",
        ]
    )
    overall = uefa.get("overall") or {}
    lines.append(
        f"| **UEFA overall** | {overall.get('player_lineup_top3')} | {overall.get('player_team_top3')} | "
        f"{overall.get('improvement_pp')} |"
    )
    for league, m in (uefa.get("by_league") or {}).items():
        lines.append(
            f"| {league} | {m.get('player_lineup_top3')} | {m.get('player_team_top3')} | {m.get('improvement_pp')} |"
        )
    lines.append(f"\n54Q baseline UEFA composite: **{overall.get('baseline_54q_proxy_top3')}**")

    lines.extend(
        [
            "",
            "## Part F — Elite recheck",
            "",
            f"| Check | Value |",
            f"|-------|-------|",
            f"| UEFA player+team top-3 | {elite.get('uefa_player_team_top3')} |",
            f"| Elite threshold | {elite.get('elite_threshold')} |",
            f"| Reaches elite | **{elite.get('reaches_elite')}** |",
            f"| Best test group | {elite.get('best_test_group')} ({elite.get('best_test_top3')}) |",
            "",
            "## Part G — Decision questions",
            "",
            f"1. **Does team context help?** {decision.get('team_context_helps')} (lift {decision.get('team_lift_test_top3_pp')} pp test; UEFA +{decision.get('uefa_improvement_pp')} pp)",
            f"2. **Which team features matter?** {len(feat_imp.get('positive') or [])} positive — top: {(feat_imp.get('ranked') or [['n/a', 0]])[0][0]}",
            f"3. **Does UEFA improve?** {float(decision.get('uefa_improvement_pp') or 0) > 0}",
            f"4. **Still HIGH_VALUE?** {rec in ('GOALSCORER_HIGH_VALUE', 'GOALSCORER_MAXED_OUT')}",
            f"5. **Elite realistic?** {elite.get('reaches_elite')}",
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No production, deploy, WDE, SaaS, or live prediction changes",
            "- No EGIE scoring changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
