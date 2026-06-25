#!/usr/bin/env python3
"""Phase 60C — Goal event backfill, timing re-research, odds buckets, highlights cache."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.goal_event_backfill import GoalEventBackfillRunner, write_backfill_artifacts
from worldcup_predictor.research.highlights_service import build_highlights_payload, cache_highlights_payload
from worldcup_predictor.research.odds_bucket_research import OddsBucketResearch, write_odds_artifacts

REPORT = ROOT / "PHASE_60C_GOAL_EVENT_BACKFILL_RESEARCH_HIGHLIGHTS_REPORT.md"


def _recommendation(backfill: dict, odds: dict) -> str:
    comparison = backfill.get("comparison") or {}
    backfilled = sum(1 for r in backfill.get("results", []) if r.events_added > 0)
    if backfilled > 0 and odds.get("sample_size", 0) > 0:
        return "RESEARCH_PAGE_READY"
    if backfilled > 0:
        return "BACKFILL_PARTIAL_READY"
    if backfill.get("api_calls_used", 0) == 0 and comparison.get("reliable_delta", 0) == 0:
        return "NEEDS_MORE_API_DATA"
    return "BACKFILL_PARTIAL_READY"


def _write_report(
    *,
    backfill_output: dict,
    odds_output: dict,
    artifact_dir: Path,
    recommendation: str,
) -> None:
    comp = backfill_output.get("comparison") or {}
    before = backfill_output.get("before_summary") or {}
    after = backfill_output.get("after_summary") or {}
    results = backfill_output.get("results") or []
    added = sum(1 for r in results if r.events_added > 0)
    candidates = backfill_output.get("candidates") or []

    lines = [
        "# Phase 60C — Goal Event Backfill + Research Highlights Report",
        "",
        f"**Recommendation:** `{recommendation}`",
        "",
        "## Part A — Backfill",
        "",
        f"- Backfill candidates: **{len(candidates)}**",
        f"- Fixtures backfilled: **{added}**",
        f"- Events added: **{sum(r.events_added for r in results)}**",
        f"- API calls used: **{backfill_output.get('api_calls_used', 0)}**",
        "",
        "## Part B — First goal timing (before vs after)",
        "",
        f"| Metric | Before | After |",
        f"|--------|-------:|------:|",
        f"| Reliable fixtures | {comp.get('reliable_fixtures_before')} | {comp.get('reliable_fixtures_after')} |",
        f"| Excluded (data missing) | {comp.get('excluded_before')} | {comp.get('excluded_after')} |",
        f"| 1–30% (with goal) | {comp.get('pct_1_30_with_goal_before')}% | {comp.get('pct_1_30_with_goal_after')}% |",
        f"| 31+% (with goal) | {comp.get('pct_31_plus_with_goal_before')}% | {comp.get('pct_31_plus_with_goal_after')}% |",
        f"| No-goal % | {comp.get('pct_no_goal_before')}% | {comp.get('pct_no_goal_after')}% |",
        "",
        "## Part C — Odds bucket research",
        "",
        f"- Sample size (fixtures with odds): **{odds_output.get('sample_size', 0)}**",
        "",
    ]
    for label, stats in (odds_output.get("favorite_bucket_stats") or {}).items():
        if stats.get("match_count", 0) > 0:
            lines.append(
                f"- **{label}**: n={stats['match_count']}, fav_win={stats.get('favorite_win_pct')}%, "
                f"O2.5={stats.get('over_25_pct')}%, BTTS={stats.get('btts_yes_pct')}%"
            )

    lines.extend(
        [
            "",
            "## Part D/E — Page & API",
            "",
            "- Route: `/research/highlights` (public-safe)",
            "- API: `GET /api/research/highlights`",
            "",
            "## Part F — Artifacts",
            "",
            f"- `{artifact_dir}/`",
            "",
            "## Safety",
            "",
            "- No WDE / prediction engine / SaaS / shadow changes",
            "- No deploy in this phase (validation must pass first)",
            "",
            "**STOP — Phase 60C complete.**",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    runner = GoalEventBackfillRunner()
    print("Starting backfill...", flush=True)
    backfill_output = runner.run()
    print("Backfill done, running odds research...", flush=True)
    artifact_dir = write_backfill_artifacts(backfill_output)

    odds_research = OddsBucketResearch()
    odds_output = odds_research.run()
    write_odds_artifacts(odds_output)

    highlights = build_highlights_payload()
    cache_highlights_payload(highlights)

    recommendation = _recommendation(backfill_output, odds_output)
    _write_report(
        backfill_output=backfill_output,
        odds_output=odds_output,
        artifact_dir=artifact_dir,
        recommendation=recommendation,
    )

    comp = backfill_output["comparison"]
    print(f"CANDIDATES: {len(backfill_output['candidates'])}")
    print(f"BACKFILLED: {sum(1 for r in backfill_output['results'] if r.events_added > 0)}")
    print(f"API_CALLS: {backfill_output['api_calls_used']}")
    print(f"RELIABLE_BEFORE: {comp.get('reliable_fixtures_before')}")
    print(f"RELIABLE_AFTER: {comp.get('reliable_fixtures_after')}")
    print(f"ODDS_SAMPLE: {odds_output.get('sample_size')}")
    print(f"RECOMMENDATION: {recommendation}")
    print(f"ARTIFACTS: {artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
