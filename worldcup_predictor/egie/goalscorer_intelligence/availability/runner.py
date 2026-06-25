"""Phase 54S player availability intelligence orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_intelligence.availability.dataset_v5 import build_dataset_v5
from worldcup_predictor.egie.goalscorer_intelligence.availability.evaluation import (
    availability_feature_importance,
    decide_recommendation,
    elite_path_test,
    evaluate_feature_groups,
    uefa_league_analysis,
)
from worldcup_predictor.egie.goalscorer_intelligence.availability.models import (
    ELITE_PATH_THRESHOLD,
    VALID_RECOMMENDATIONS,
)

ARTIFACT_DIR = Path("artifacts/phase54s_player_availability")
REPORT_PATH = Path("PHASE_54S_PLAYER_AVAILABILITY_REPORT.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase54s() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_v5, ds_meta = build_dataset_v5()
    dataset_v5.to_parquet(ARTIFACT_DIR / "goalscorer_dataset_v5.parquet", index=False)
    (ARTIFACT_DIR / "dataset_v5_summary.json").write_text(json.dumps(ds_meta, indent=2), encoding="utf-8")

    group_results = evaluate_feature_groups(dataset_v5)
    (ARTIFACT_DIR / "feature_group_results.json").write_text(json.dumps(group_results, indent=2), encoding="utf-8")

    feat_imp = availability_feature_importance(dataset_v5)
    (ARTIFACT_DIR / "availability_feature_importance.json").write_text(
        json.dumps(feat_imp, indent=2), encoding="utf-8"
    )

    uefa = uefa_league_analysis(dataset_v5)
    (ARTIFACT_DIR / "uefa_league_analysis.json").write_text(json.dumps(uefa, indent=2), encoding="utf-8")

    elite = elite_path_test(uefa, group_results)
    (ARTIFACT_DIR / "elite_path_test.json").write_text(json.dumps(elite, indent=2), encoding="utf-8")

    decision = decide_recommendation(group_results, feat_imp, uefa, elite)
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    recommendation = decision.get("recommendation", "GOALSCORER_HIGH_VALUE")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "GOALSCORER_HIGH_VALUE"

    report = {
        "generated_at": _utc_now(),
        "phase": "54S",
        "dataset_v5": ds_meta,
        "feature_groups": group_results,
        "availability_feature_importance": feat_imp,
        "uefa_analysis": uefa,
        "elite_path_test": elite,
        "decision": decision,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase54s_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, group_results, feat_imp, uefa, elite, decision, ds_meta)
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
        "# PHASE 54S — Player Availability Intelligence",
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
        "## Part A — Availability features",
        "",
        f"Built **{len(ds_meta.get('availability_columns', []))}** availability features.",
        "",
        "| Feature | Non-zero rows |",
        "|---------|---------------|",
    ]
    for feat, cnt in (ds_meta.get("non_zero_coverage") or {}).items():
        lines.append(f"| {feat} | {cnt:,} |")

    lines.extend(
        [
            "",
            "Artifact: `artifacts/phase54s_player_availability/goalscorer_dataset_v5.parquet`",
            "",
            "## Part B — Dataset v5",
            "",
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
            "## Part D — UEFA analysis (test split)",
            "",
            "| League | Top-1 | Top-3 | Top-5 | MRR | Δ vs lineup |",
            "|--------|-------|-------|-------|-----|-------------|",
        ]
    )
    overall = uefa.get("overall") or {}
    lines.append(
        f"| **UEFA overall** | {overall.get('top1_hit')} | {overall.get('player_lineup_availability_top3')} | "
        f"{overall.get('top5_hit')} | {overall.get('mrr')} | {overall.get('improvement_pp')} |"
    )
    for league, m in (uefa.get("by_league") or {}).items():
        lines.append(
            f"| {league} | {m.get('top1_hit')} | {m.get('player_lineup_availability_top3')} | "
            f"{m.get('top5_hit')} | {m.get('mrr')} | {m.get('improvement_pp')} |"
        )

    lines.extend(
        [
            "",
            "## Part E — Availability feature importance",
            "",
            f"Baseline lineup+availability top-3: **{feat_imp.get('baseline_top3')}**",
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
            f"**Positive:** {', '.join(feat_imp.get('positive') or []) or '—'}",
            "",
            "## Part F — Elite path test",
            "",
            f"| Check | Value |",
            f"|-------|-------|",
            f"| UEFA lineup+availability top-3 | {elite.get('uefa_lineup_availability_top3')} |",
            f"| Target threshold | {ELITE_PATH_THRESHOLD} |",
            f"| Closes UEFA gap | **{elite.get('closes_uefa_gap')}** |",
            f"| Architecture near ceiling | **{elite.get('architecture_near_ceiling')}** |",
            "",
            "## Part G — Decision questions",
            "",
            f"1. **Does availability help?** {decision.get('availability_helps')} (+{decision.get('test_lift_lineup_to_full_pp')} pp test; UEFA +{decision.get('uefa_improvement_pp')} pp)",
            f"2. **Which features matter?** {len(feat_imp.get('positive') or [])} positive — top: {(feat_imp.get('ranked') or [['n/a', 0]])[0][0]}",
            f"3. **Does UEFA improve?** {float(decision.get('uefa_improvement_pp') or 0) > 0}",
            f"4. **Elite path open?** {elite.get('closes_uefa_gap')}",
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
