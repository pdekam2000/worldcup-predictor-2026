"""Phase 54Q generalization orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.egie.goalscorer_intelligence.dataset_v3 import build_dataset_v3
from worldcup_predictor.egie.goalscorer_intelligence.generalization import (
    confidence_stability,
    elite_candidate_test,
    league_split_validation,
    prepare_intelligence_frame,
    robustness_audit,
    tier_reliability,
)
from worldcup_predictor.egie.goalscorer_intelligence.generalization_models import VALID_RECOMMENDATIONS
from worldcup_predictor.egie.goalscorer_intelligence.validation import fixture_ranking_hits, run_historical_replay

ARTIFACT_DIR = Path("artifacts/phase54q_goalscorer_generalization")
REPORT_PATH = Path("PHASE_54Q_GOALSCORER_GENERALIZATION_REPORT.md")
P54P_REPLAY = Path("artifacts/phase54p_goalscorer_intelligence/historical_replay.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase54q() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_v3, ds_meta = build_dataset_v3()
    dataset_v3.to_parquet(ARTIFACT_DIR / "goalscorer_dataset_v3.parquet", index=False)
    (ARTIFACT_DIR / "dataset_v3_summary.json").write_text(json.dumps(ds_meta, indent=2), encoding="utf-8")

    intel_df = prepare_intelligence_frame(dataset_v3)
    intel_df.to_parquet(ARTIFACT_DIR / "goalscorer_intelligence_v3.parquet", index=False)

    overall_replay = run_historical_replay(intel_df)
    (ARTIFACT_DIR / "overall_replay.json").write_text(json.dumps(overall_replay, indent=2, default=str), encoding="utf-8")

    league_results = league_split_validation(intel_df)
    (ARTIFACT_DIR / "league_split.json").write_text(json.dumps(league_results, indent=2), encoding="utf-8")

    conf_stability = confidence_stability(intel_df)
    (ARTIFACT_DIR / "confidence_stability.json").write_text(json.dumps(conf_stability, indent=2), encoding="utf-8")

    robustness = robustness_audit(intel_df)
    (ARTIFACT_DIR / "robustness_audit.json").write_text(json.dumps(robustness, indent=2), encoding="utf-8")

    tier_rel = tier_reliability(intel_df)
    (ARTIFACT_DIR / "tier_reliability.json").write_text(json.dumps(tier_rel, indent=2), encoding="utf-8")

    wc_only_top3 = None
    if P54P_REPLAY.is_file():
        p54p = json.loads(P54P_REPLAY.read_text(encoding="utf-8"))
        wc_only_top3 = float(
            ((p54p.get("markets") or {}).get("anytime") or {}).get("composite_scorer", {}).get("top3_hit", 0)
        )

    anytime_comp = (overall_replay.get("markets") or {}).get("anytime") or {}
    elite = elite_candidate_test(
        anytime_comp,
        league_results,
        conf_stability,
        robustness,
        wc_only_top3=wc_only_top3,
    )
    (ARTIFACT_DIR / "elite_candidate_test.json").write_text(json.dumps(elite, indent=2), encoding="utf-8")

    recommendation = elite.get("recommendation", "GOALSCORER_HIGH_VALUE")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "GOALSCORER_HIGH_VALUE"

    report = {
        "generated_at": _utc_now(),
        "phase": "54Q",
        "dataset_v3": ds_meta,
        "overall_replay": overall_replay,
        "league_split": league_results,
        "confidence_stability": conf_stability,
        "robustness": robustness,
        "tier_reliability": tier_rel,
        "elite_test": elite,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase54q_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_report(report, elite, league_results, conf_stability, robustness, tier_rel, ds_meta)
    return report


def _write_report(
    report: dict[str, Any],
    elite: dict[str, Any],
    leagues: dict[str, Any],
    conf: dict[str, Any],
    robust: dict[str, Any],
    tiers: dict[str, Any],
    ds_meta: dict[str, Any],
) -> None:
    anytime = (report.get("overall_replay") or {}).get("markets", {}).get("anytime", {})
    comp = anytime.get("composite_scorer") or {}

    lines = [
        "# PHASE 54Q — Goalscorer Intelligence Stress Test & Generalization",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Large-Scale Validation → Cross-League → Stability Audit  ",
        "**Status:** Complete — research only  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{report.get('recommendation')}`**",
        "",
        "---",
        "",
        "## Part A — Dataset expansion",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| **Fixtures** | **{ds_meta.get('fixtures')}** |",
        f"| Rows | {ds_meta.get('rows'):,} |",
        f"| With goalscorer odds | {ds_meta.get('fixtures_with_odds')} |",
        f"| Meets 100+ target | {ds_meta.get('meets_100_fixtures')} |",
        f"| Meets 200+ target | {ds_meta.get('meets_200_fixtures')} |",
        "",
        "Artifact: `artifacts/phase54q_goalscorer_generalization/goalscorer_dataset_v3.parquet`",
        "",
        "## Part B — League split validation",
        "",
        "| League | Fixtures | Evaluated | Top-1 | Top-3 | Top-5 |",
        "|--------|----------|-----------|-------|-------|-------|",
    ]
    for label, m in leagues.items():
        lines.append(
            f"| {label} | {m.get('fixtures')} | {m.get('fixtures_evaluated')} | "
            f"{m.get('top1_hit')} | {m.get('top3_hit')} | {m.get('top5_hit')} |"
        )

    lines.extend(
        [
            "",
            f"**Overall composite top-3:** {comp.get('top3_hit', 'n/a')}",
            "",
            "## Part C — Confidence stability",
            "",
            "| Tier | Top-3 hit |",
            "|------|-----------|",
        ]
    )
    for tier, val in (conf.get("top3_by_tier") or {}).items():
        lines.append(f"| {tier} | {val} |")
    lines.extend(
        [
            "",
            f"Monotonic ordering: **{conf.get('monotonic_ordering')}**  ",
            f"Tier A superior: **{conf.get('tier_a_superior')}**",
            "",
            "## Part D — Robustness audit",
            "",
            "| Scenario | Top-3 | Drop vs baseline |",
            "|----------|-------|------------------|",
        ]
    )
    for s in robust.get("scenarios") or []:
        lines.append(f"| {s.get('scenario')} | {s.get('top3_hit')} | {s.get('top3_drop')} |")
    lines.append(f"\n**Primary feature carrier:** {robust.get('primary_carrier')}")

    lines.extend(["", "## Part E — Tier reliability", "", "| Tier | Samples | Fixtures | Hit rate | Brier | ECE |", "|------|---------|----------|----------|-------|-----|"])
    for t in tiers.get("tiers") or []:
        lines.append(
            f"| {t.get('tier')} | {t.get('sample_count')} | {t.get('fixture_count')} | "
            f"{t.get('hit_rate')} | {t.get('brier')} | {t.get('ece')} |"
        )

    checks = elite.get("checks") or {}
    lines.extend(
        [
            "",
            "## Part F — Elite candidate test",
            "",
            f"| Check | Pass |",
            f"|-------|------|",
        ]
    )
    for k, v in checks.items():
        lines.append(f"| {k} | {v} |")

    lines.extend(
        [
            "",
            "## Part G — Decision questions",
            "",
            f"1. **Survives expansion?** Overall top-3 = {comp.get('top3_hit')} on {ds_meta.get('fixtures')} fixtures (WC-only was {elite.get('wc_only_top3')})",
            f"2. **Best league:** {max(leagues.items(), key=lambda x: x[1].get('top3_hit', 0))[0] if leagues else 'n/a'}",
            f"3. **Tiers trustworthy?** Monotonic={conf.get('monotonic_ordering')}, Tier A superior={conf.get('tier_a_superior')}",
            f"4. **Key feature family:** {robust.get('primary_carrier')}",
            f"5. **Truly elite?** {report.get('recommendation')}",
            "",
            f"### Final recommendation: **`{report.get('recommendation')}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No production, WDE, SaaS, deploy",
            "- No live prediction or EGIE scoring changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
