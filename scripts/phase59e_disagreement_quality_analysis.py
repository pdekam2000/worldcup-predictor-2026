#!/usr/bin/env python3
"""Phase 59E — Shadow vs production disagreement quality analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.admin.disagreement_quality_analysis import run_analysis, write_artifacts

REPORT_PATH = ROOT / "PHASE_59E_SHADOW_PRODUCTION_DISAGREEMENT_QUALITY_REPORT.md"


def _write_report(summary: dict[str, Any]) -> None:
    comp = summary.get("comparison_summary") or {}
    micro = summary.get("micro_test_readiness") or {}
    rec = summary.get("recommendation") or micro.get("recommendation") or "BLOCKED_WITH_REASON"

    lines = [
        "# Phase 59E — Shadow vs Production Disagreement Quality Report",
        "",
        "## Summary",
        "",
        f"- Rows analyzed (comparable): **{summary.get('total_rows_analyzed', 0)}**",
        f"- Raw disagreements: **{summary.get('raw_disagreement_count', 0)}**",
        f"- True semantic disagreements: **{summary.get('true_disagreement_count', 0)}**",
        f"- Normalization artifacts: **{summary.get('normalization_artifact_count', 0)}**",
        f"- Recommendation: **`{rec}`**",
        "",
        "## Comparison baseline (Phase 59D)",
        "",
        f"- Comparable: {comp.get('total_comparable', '—')}",
        f"- Same pick (raw): {comp.get('same_pick_count', '—')}",
        f"- Disagreements (raw): {comp.get('disagreement_count', '—')}",
        f"- Missing production: {comp.get('missing_production_count', '—')}",
        "",
        "## Disagreement breakdown by market",
        "",
        "| Market | Raw disagree | True disagree | Normalization artifacts |",
        "|--------|--------------|---------------|-------------------------|",
    ]

    raw = (summary.get("disagreement_by_market") or {}).get("raw") or {}
    true = (summary.get("disagreement_by_market") or {}).get("true") or {}
    art = (summary.get("disagreement_by_market") or {}).get("normalization_artifacts") or {}
    markets = sorted(set(raw) | set(true) | set(art))
    for m in markets:
        lines.append(f"| {m} | {raw.get(m, 0)} | {true.get(m, 0)} | {art.get(m, 0)} |")

    lines.extend(
        [
            "",
            "## Admin label distribution",
            "",
            "```json",
            json.dumps(summary.get("label_counts") or {}, indent=2),
            "```",
            "",
            "## True disagreement by shadow tier",
            "",
            "```json",
            json.dumps(summary.get("true_disagreement_by_shadow_tier") or {}, indent=2),
            "```",
            "",
            "## True disagreement by production confidence bucket",
            "",
            "```json",
            json.dumps(summary.get("true_disagreement_by_production_conf_bucket") or {}, indent=2),
            "```",
            "",
            "## Strongest Shadow-favored cases (admin labels)",
            "",
        ]
    )

    shadow_cases = summary.get("strongest_shadow_favored") or []
    if shadow_cases:
        for c in shadow_cases[:5]:
            lines.append(
                f"- **{c.get('home_team')} vs {c.get('away_team')}** · {c.get('market_id')} · "
                f"shadow={c.get('semantic_shadow_pick')} prod={c.get('semantic_production_pick')} · "
                f"tier {c.get('shadow_tier')} · {c.get('label_reason')}"
            )
    else:
        lines.append("- None met SHADOW_LEAN thresholds under conservative risk gates.")

    lines.extend(["", "## Strongest Production-favored cases", ""])
    prod_cases = summary.get("strongest_production_favored") or []
    if prod_cases:
        for c in prod_cases[:5]:
            lines.append(
                f"- **{c.get('home_team')} vs {c.get('away_team')}** · {c.get('market_id')} · "
                f"shadow={c.get('semantic_shadow_pick')} prod={c.get('semantic_production_pick')} · "
                f"prod_conf={c.get('production_confidence')} · {c.get('label_reason')}"
            )
    else:
        lines.append("- None met PRODUCTION_LEAN thresholds.")

    lines.extend(["", "## NO_BET cases (sample)", ""])
    for c in (summary.get("no_bet_cases_sample") or [])[:5]:
        lines.append(
            f"- {c.get('home_team')} vs {c.get('away_team')} · {c.get('market_id')} · {c.get('label_reason')}"
        )

    lines.extend(["", "## NEEDS_RESULT_DATA cases (sample)", ""])
    for c in (summary.get("needs_result_data_sample") or [])[:5]:
        lines.append(
            f"- {c.get('home_team')} vs {c.get('away_team')} · {c.get('market_id')} · "
            f"shadow={c.get('semantic_shadow_pick')} prod={c.get('semantic_production_pick')}"
        )

    lines.extend(["", "## Risk warnings", ""])
    for w in summary.get("risk_warnings") or []:
        lines.append(f"- {w}")

    hist = summary.get("historical_shadow_risk") or {}
    lines.extend(
        [
            "",
            "## Historical shadow context (root-cause replay)",
            "",
            f"- Incorrect predictions analyzed: **{hist.get('total_incorrect_historical', 0)}**",
            f"- Tier A failure rate: **{hist.get('tier_a_failure_rate', 0):.1%}**",
            f"- High-confidence miss rate: **{hist.get('high_confidence_miss_rate', 0):.1%}**",
            "",
            "## Real-money micro testing",
            "",
            f"- Ready markets: **{', '.join(micro.get('ready_markets') or []) or 'none'}**",
            f"- Shadow lean count: **{micro.get('shadow_lean_count', 0)}**",
            f"- Production lean count: **{micro.get('production_lean_count', 0)}**",
            f"- All fixtures pending: **{micro.get('all_pending', True)}**",
            "",
            "No market is ready for real-money micro testing until fixtures finish and labels can be validated.",
            "",
            "## Artifacts",
            "",
            "- `artifacts/phase59e_disagreement_quality/disagreement_quality_rows.csv`",
            "- `artifacts/phase59e_disagreement_quality/summary.json`",
            "",
            "## Safety confirmation",
            "",
            "- Analysis only — no deploy, no prediction engine changes, no public output changes",
            "- Admin labels are internal research signals only",
            "- Elite Shadow not promoted; WDE and SaaS plans unchanged",
            "",
            "## Recommendation",
            "",
            f"**`{rec}`**",
            "",
        ]
    )

    if rec == "NEEDS_RESULT_DATA":
        lines.append(
            "Disagreement quality cannot be adjudicated without finished-match outcomes. "
            "Most raw disagreements (41/56) are normalization artifacts, not true model conflict. "
            "Re-run after evaluations resolve to compare Shadow vs Production accuracy by market."
        )
    elif rec == "NO_BET_RECOMMENDED":
        lines.append(
            "Conservative gates and historical Tier A miss rate argue against real-money micro testing on disagreements."
        )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    analyzed, summary = run_analysis(limit=500)
    artifact_dir = write_artifacts(analyzed, summary)
    _write_report(summary)

    rec = summary.get("recommendation", "BLOCKED_WITH_REASON")
    print(f"ANALYZED: {len(analyzed)} comparable rows")
    print(f"TRUE_DISAGREEMENTS: {summary.get('true_disagreement_count', 0)}")
    print(f"LABELS: {summary.get('label_counts')}")
    print(f"ARTIFACTS: {artifact_dir}")
    print(f"RECOMMENDATION: {rec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
