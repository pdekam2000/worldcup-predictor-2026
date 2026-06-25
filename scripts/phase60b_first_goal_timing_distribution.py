#!/usr/bin/env python3
"""Phase 60B — First goal timing distribution research."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.first_goal_timing_distribution import (
    ARTIFACT_DIR,
    FirstGoalTimingResearch,
    write_artifacts,
)

REPORT = ROOT / "PHASE_60B_FIRST_GOAL_TIMING_DISTRIBUTION_REPORT.md"


def _write_report(summary: dict) -> None:
    main = summary.get("main_answer") or {}
    a = main.get("among_fixtures_with_at_least_one_goal") or {}
    b = main.get("among_all_reliable_completed_fixtures") or {}
    overall = summary.get("overall") or {}
    buckets = overall.get("bucket_counts") or {}
    rec = summary.get("recommendation", "NEEDS_MORE_DATA")
    quality = summary.get("data_quality") or {}

    lines = [
        "# Phase 60B — First Goal Timing Distribution Report",
        "",
        "## Summary",
        "",
        f"- Recommendation: **`{rec}`**",
        f"- Database: `{summary.get('db_path', '')}`",
        f"- API calls used: **{summary.get('api_calls_used', 0)}**",
        "",
        "## Main question",
        "",
        "**Among fixtures with at least one goal:**",
        f"- First goal in minutes **1–30**: **{a.get('first_goal_1_30_pct', '—')}%** ({overall.get('first_goal_1_30_count', 0)} / {a.get('sample_size', 0)})",
        f"- First goal **after minute 30**: **{a.get('first_goal_31_plus_pct', '—')}%** ({overall.get('first_goal_31_plus_count', 0)} / {a.get('sample_size', 0)})",
        "",
        "**Among all reliable completed fixtures (includes 0-0):**",
        f"- First goal **1–30**: **{b.get('first_goal_1_30_pct', '—')}%**",
        f"- First goal **31+**: **{b.get('first_goal_31_plus_pct', '—')}%**",
        f"- **No goal (0-0)**: **{b.get('no_goal_pct', '—')}%** ({overall.get('no_goal_fixtures', 0)} fixtures)",
        "",
        f"- Total reliable fixtures analyzed: **{overall.get('total_reliable_fixtures', 0)}**",
        f"- Data missing (excluded from percentages): **{overall.get('data_missing_fixtures', 0)}**",
        "",
        "## Detailed minute buckets (reliable fixtures)",
        "",
        "| Bucket | Count | % of reliable |",
        "|--------|------:|--------------:|",
    ]
    for label, count in buckets.items():
        pct = (overall.get("bucket_pct_of_reliable") or {}).get(label)
        lines.append(f"| {label} | {count} | {pct if pct is not None else '—'}% |")

    lines.extend(["", "## By league (top competitions)", ""])
    for league, stats in list((summary.get("by_league") or {}).items())[:8]:
        lines.append(
            f"- **{league}**: reliable={stats.get('total_reliable_fixtures')}, "
            f"with_goal={stats.get('with_at_least_one_goal')}, "
            f"1-30={stats.get('pct_A_with_goal_first_1_30')}%, "
            f"31+={stats.get('pct_A_with_goal_first_31_plus')}%, "
            f"no_goal={stats.get('pct_B_no_goal')}%"
        )

    lines.extend(["", "## By data source", ""])
    for src, stats in (summary.get("by_source") or {}).items():
        lines.append(
            f"- **{src}**: with_goal={stats.get('with_at_least_one_goal')}, "
            f"1-30={stats.get('pct_A_with_goal_first_1_30')}%, "
            f"31+={stats.get('pct_A_with_goal_first_31_plus')}%"
        )

    lines.extend(["", "## Data quality", ""])
    lines.append(f"- Fixtures skipped (scored, no events): **{quality.get('fixtures_skipped_missing_events', 0)}**")
    lines.append(f"- Score vs event inconsistencies: **{quality.get('fixtures_score_event_inconsistent', 0)}**")
    lines.append(f"- Goal events with missing minute: **{quality.get('events_missing_minute', 0)}**")
    lines.append(f"- Sources: {', '.join(quality.get('sources_used') or [])}")
    lines.extend(
        [
            "",
            "## EGIE goal timing model recommendation",
            "",
            f"**`{rec}`**",
            "",
        ]
    )
    if rec == "USE_1_30_PRIOR":
        lines.append(
            "Overall first-goal timing is materially front-loaded (roughly half of opening goals land in minutes 1–30). "
            "A global 1–30 vs 31+ prior is reasonable as a baseline for EGIE goal-timing buckets."
        )
    elif rec == "USE_LEAGUE_SPECIFIC_PRIORS":
        lines.append(
            "League-level timing differs enough to prefer competition-specific priors over one global 1–30 split."
        )
    else:
        lines.append("Expand goal-event coverage before tightening model priors.")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `artifacts/phase60b_first_goal_timing_distribution/first_goal_timing_rows.csv`",
            "- `artifacts/phase60b_first_goal_timing_distribution/first_goal_timing_summary.json`",
            "- `artifacts/phase60b_first_goal_timing_distribution/first_goal_timing_by_league.csv`",
            "- `artifacts/phase60b_first_goal_timing_distribution/first_goal_timing_by_season.csv`",
            "- `artifacts/phase60b_first_goal_timing_distribution/data_quality_report.json`",
            "",
            "## Safety",
            "",
            "- Research only — no prediction engine, WDE, public output, or SaaS changes",
            "- No deploy",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    research = FirstGoalTimingResearch()
    result = research.run()
    artifact_dir = write_artifacts(result)
    _write_report(result["summary"])

    s = result["summary"]
    main_a = s["main_answer"]["among_fixtures_with_at_least_one_goal"]
    print(f"RELIABLE: {s['overall']['total_reliable_fixtures']}")
    print(f"WITH_GOAL: {s['overall']['with_at_least_one_goal']}")
    print(f"1-30% (with goal): {main_a['first_goal_1_30_pct']}")
    print(f"31+% (with goal): {main_a['first_goal_31_plus_pct']}")
    print(f"NO_GOAL%: {s['overall']['pct_B_no_goal']}")
    print(f"ARTIFACTS: {artifact_dir}")
    print(f"RECOMMENDATION: {s['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
