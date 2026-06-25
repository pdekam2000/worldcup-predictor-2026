"""Phase 54Q-1 UEFA goalscorer odds audit orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.coverage import (
    scan_dataset_v3_coverage,
    scan_sportmonks_goalscorer_coverage,
)
from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.impact import (
    compare_wc_vs_uefa,
    counterfactual_uefa_with_odds,
    decide_limitation,
    feature_contribution_audit,
    odds_lift_on_wc,
)
from worldcup_predictor.egie.goalscorer_intelligence.uefa_odds_audit.models import VALID_RECOMMENDATIONS

ARTIFACT_DIR = Path("artifacts/phase54q1_uefa_goalscorer_odds_audit")
REPORT_PATH = Path("PHASE_54Q1_UEFA_GOALSCORER_ODDS_AUDIT_REPORT.md")
V3_INTEL = Path("artifacts/phase54q_goalscorer_generalization/goalscorer_intelligence_v3.parquet")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_phase54q1() -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    if not V3_INTEL.is_file():
        from worldcup_predictor.egie.goalscorer_intelligence.stress_runner import run_phase54q

        run_phase54q()

    df = pd.read_parquet(V3_INTEL)

    cache_coverage = scan_sportmonks_goalscorer_coverage()
    dataset_coverage = scan_dataset_v3_coverage(df)
    coverage = {"sportmonks_cache": cache_coverage, "dataset_v3": dataset_coverage}
    (ARTIFACT_DIR / "uefa_odds_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    comparison = compare_wc_vs_uefa(df)
    (ARTIFACT_DIR / "wc_vs_uefa_comparison.json").write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")

    wc_lift = odds_lift_on_wc(df)
    (ARTIFACT_DIR / "wc_odds_lift.json").write_text(json.dumps(wc_lift, indent=2), encoding="utf-8")

    counterfactual = counterfactual_uefa_with_odds(df, wc_lift)
    (ARTIFACT_DIR / "counterfactual_analysis.json").write_text(json.dumps(counterfactual, indent=2), encoding="utf-8")

    features = feature_contribution_audit(df)
    (ARTIFACT_DIR / "feature_contribution.json").write_text(json.dumps(features, indent=2), encoding="utf-8")

    decision = decide_limitation(comparison, wc_lift, counterfactual, coverage, features)
    (ARTIFACT_DIR / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    recommendation = decision.get("recommendation", "BOTH_LIMITED")
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "BOTH_LIMITED"

    report = {
        "generated_at": _utc_now(),
        "phase": "54Q-1",
        "coverage": coverage,
        "comparison": comparison,
        "wc_odds_lift": wc_lift,
        "counterfactual": counterfactual,
        "feature_contribution": features,
        "decision": decision,
        "recommendation": recommendation,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase54q1_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, coverage, comparison, wc_lift, counterfactual, features, decision, recommendation)
    return report


def _write_markdown(
    report: dict[str, Any],
    coverage: dict[str, Any],
    comparison: dict[str, Any],
    wc_lift: dict[str, Any],
    counterfactual: dict[str, Any],
    features: dict[str, Any],
    decision: dict[str, Any],
    recommendation: str,
) -> None:
    cache_leagues = (coverage.get("sportmonks_cache") or {}).get("leagues") or {}
    ds_leagues = (coverage.get("dataset_v3") or {}).get("by_league") or {}
    ev = decision.get("evidence") or {}

    def _top3(seg: str, track: str = "composite") -> str:
        return str(
            ((comparison.get(seg) or {}).get(track) or {})
            .get("ranking", {})
            .get("top3_hit", "n/a")
        )

    lines = [
        "# PHASE 54Q-1 — UEFA Goalscorer Odds Coverage Audit",
        "",
        f"**Date:** {report.get('generated_at', '')[:10]}  ",
        "**Mode:** Coverage Audit → Impact Analysis → Report  ",
        "**Status:** Complete — research only  ",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{recommendation}`**",
        "",
        f"**Primary limitation:** {decision.get('primary_limitation')} (A=model, B=odds, C=both)",
        "",
        "---",
        "",
        "## Part A — UEFA odds coverage",
        "",
        "### Sportmonks cache (strict goalscorer markets)",
        "",
        "| League | Fixtures | With GS odds | Coverage % | Bookmakers |",
        "|--------|----------|--------------|------------|------------|",
    ]
    for league in ("champions_league", "europa_league", "conference_league", "world_cup"):
        m = cache_leagues.get(league) or {}
        books = ", ".join((m.get("bookmakers") or {}).keys()) or "—"
        lines.append(
            f"| {league} | {m.get('fixtures', 0)} | {m.get('fixtures_with_strict_goalscorer_odds', 0)} | "
            f"{m.get('coverage_pct_strict', 0):.1%} | {books} |"
        )

    lines.extend(
        [
            "",
            "### Dataset v3 (API-Football WC bridge overlay)",
            "",
            "| League | Fixtures | With odds | Coverage % |",
            "|--------|----------|-----------|------------|",
        ]
    )
    for league in ("champions_league", "europa_league", "conference_league", "world_cup"):
        m = ds_leagues.get(league) or {}
        lines.append(
            f"| {league} | {m.get('fixtures', 0)} | {m.get('fixtures_with_goalscorer_odds', 0)} | "
            f"{m.get('coverage_pct', 0):.1%} |"
        )

    lines.extend(
        [
            "",
            f"**UEFA dataset v3 coverage:** {(coverage.get('dataset_v3') or {}).get('uefa_coverage_pct', 0):.1%}",
            "",
            "## Part B — WC vs UEFA comparison",
            "",
            "| Segment | Fixtures | Composite Top-3 | Top-5 | ML Top-3 | Blend Top-3 |",
            "|---------|----------|-----------------|-------|----------|-------------|",
            f"| WC with odds | {(comparison.get('world_cup_with_odds') or {}).get('fixtures', 0)} | {_top3('world_cup_with_odds')} | "
            f"{((comparison.get('world_cup_with_odds') or {}).get('composite') or {}).get('ranking', {}).get('top5_hit', 'n/a')} | "
            f"{_top3('world_cup_with_odds', 'ml_only')} | {_top3('world_cup_with_odds', 'ml_odds_blend')} |",
            f"| UEFA without odds | {(comparison.get('uefa_without_odds') or {}).get('fixtures', 0)} | {_top3('uefa_without_odds')} | "
            f"{((comparison.get('uefa_without_odds') or {}).get('composite') or {}).get('ranking', {}).get('top5_hit', 'n/a')} | "
            f"{_top3('uefa_without_odds', 'ml_only')} | {_top3('uefa_without_odds', 'ml_odds_blend')} |",
            f"| UEFA all | {(comparison.get('uefa_all') or {}).get('fixtures', 0)} | {_top3('uefa_all')} | "
            f"{((comparison.get('uefa_all') or {}).get('composite') or {}).get('ranking', {}).get('top5_hit', 'n/a')} | "
            f"{_top3('uefa_all', 'ml_only')} | {_top3('uefa_all', 'ml_odds_blend')} |",
            "",
            "## Part C — Counterfactual (estimate only)",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| WC measured odds lift (blend vs ML) | {wc_lift.get('odds_lift_top3_blend_vs_ml')} |",
            f"| UEFA current ML top-3 | {counterfactual.get('uefa_current_ml_top3')} |",
            f"| UEFA current composite top-3 | {counterfactual.get('uefa_current_composite_top3')} |",
            f"| Estimated UEFA top-3 if WC odds lift applied | {counterfactual.get('estimated_if_blend_lift')} |",
            f"| Plausible range | {counterfactual.get('plausible_range_top3')} |",
            f"| Would reach 70%? | {counterfactual.get('would_reach_70pct')} |",
            "",
            "## Part D — Feature contribution (top-3 drop when removed)",
            "",
        ]
    )

    for seg in ("world_cup", "uefa", "overall"):
        fa = features.get(seg) or {}
        if not fa:
            continue
        lines.append(f"### {seg}")
        lines.append("")
        lines.append(f"Baseline top-3: {fa.get('baseline_top3')}")
        lines.append("")
        for feat, drop in fa.get("ranked_contributors") or []:
            lines.append(f"- {feat}: {drop:+.4f}")
        lines.append("")

    lines.extend(
        [
            "## Part E — Decision",
            "",
            f"| Question | Answer |",
            f"|----------|--------|",
            f"| Is engine limited by model quality? | {'Yes' if ev.get('uefa_ml_top3', 1) < 0.65 else 'Partially'} (UEFA ML top-3 = {ev.get('uefa_ml_top3')}) |",
            f"| Is engine limited by odds coverage? | {'Yes' if ev.get('uefa_odds_coverage_pct', 1) < 0.05 else 'No'} ({ev.get('uefa_odds_coverage_pct', 0):.1%} UEFA coverage) |",
            f"| WC vs UEFA top-3 gap | {ev.get('gap_wc_vs_uefa_top3')} |",
            f"| WC odds lift | {ev.get('wc_measured_odds_lift_top3')} |",
            "",
            f"### Final recommendation: **`{recommendation}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No modeling changes",
            "- No deploy, production, WDE, SaaS, or live prediction changes",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
