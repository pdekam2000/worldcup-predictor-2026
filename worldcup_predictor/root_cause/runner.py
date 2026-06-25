"""Phase 58D — Root Cause Analyzer runner."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.root_cause.attribution import attribute_failure, recommended_action_for
from worldcup_predictor.root_cause.blame_matrix import aggregate_blame_matrix, blame_row
from worldcup_predictor.root_cause.comparison import compare_evaluation_row, summarize_comparisons
from worldcup_predictor.root_cause.config import ARTIFACT_DIR, MODEL_VERSION, PHASE, REPORT_PATH
from worldcup_predictor.root_cause.data_loader import build_analysis_dataset
from worldcup_predictor.root_cause.knowledge_store import RootCauseStore
from worldcup_predictor.root_cause.models import VALID_RECOMMENDATIONS, KnowledgeRecord
from worldcup_predictor.root_cause.patterns import detect_patterns, summarize_patterns


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def decide_recommendation(
    *,
    comparisons_n: int,
    incorrect_n: int,
    pattern_summary: dict[str, Any],
    live_paired: int,
) -> str:
    if comparisons_n < 50:
        return "NEEDS_MORE_DATA"
    if not pattern_summary.get("has_clear_patterns"):
        return "NO_CLEAR_PATTERNS"
    if incorrect_n < 20:
        return "NEEDS_MORE_DATA"
    if live_paired < 5 and comparisons_n >= 200:
        return "ROOT_CAUSE_READY"
    if live_paired >= 5:
        return "ROOT_CAUSE_READY"
    return "ROOT_CAUSE_READY" if comparisons_n >= 500 else "NEEDS_MORE_DATA"


def run_phase58d(*, historical_limit: int | None = None, force_store: bool = False) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    store = RootCauseStore()
    if force_store and store.records_path.is_file():
        store.records_path.unlink()

    eval_rows, fixture_lookup, source_stats = build_analysis_dataset(historical_limit=historical_limit)

    comparisons = []
    blame_rows: list[tuple[Any, list]] = []
    attributions: list[Any] = []
    pattern_lists: list[list[str]] = []
    failure_counter: Counter[str] = Counter()

    for row in eval_rows:
        fid = int(row.get("fixture_id") or 0)
        meta = fixture_lookup.get(fid, {})
        cmp = compare_evaluation_row(row, fixture_meta=meta)
        if not cmp:
            continue
        comparisons.append(cmp)
        contribs = row.get("component_contributions") or []
        blames = blame_row(cmp, contribs)
        blame_rows.append((cmp, blames))

        if cmp.outcome == "incorrect":
            attr = attribute_failure(cmp, contributions=contribs, fixture_meta=meta)
            if attr:
                attributions.append(attr)
                failure_counter[attr.failure_reason] += 1
                patterns = detect_patterns(cmp, contributions=contribs, fixture_meta=meta, attribution=attr)
                pattern_lists.append(patterns)

                record = KnowledgeRecord(
                    fixture_id=cmp.fixture_id,
                    market=cmp.market_id,
                    failure_reason=attr.failure_reason,
                    component_scores={b.component_id: b.label for b in blames},
                    recommended_action=recommended_action_for(attr.failure_reason),
                    confidence=attr.confidence,
                    league_id=cmp.league_id,
                    season_id=cmp.season_id,
                    patterns=patterns,
                    meta={"source": row.get("source", "live_shadow"), "secondary_reasons": attr.secondary_reasons},
                )
                store.append_record(record)

    comp_summary = summarize_comparisons(comparisons)
    blame_matrix = aggregate_blame_matrix(blame_rows)
    pattern_summary = summarize_patterns(pattern_lists)

    failure_breakdown = {
        "total_incorrect": len(pattern_lists),
        "by_reason": dict(failure_counter.most_common()),
        "top_reason": failure_counter.most_common(1)[0][0] if failure_counter else None,
    }

    global_blame = blame_matrix.get("global") or {}
    top_hurt = sorted(global_blame.items(), key=lambda x: x[1].get("hurt_rate", 0), reverse=True)
    priority_actions: list[dict[str, Any]] = []
    for reason, count in failure_counter.most_common(5):
        priority_actions.append(
            {
                "failure_reason": reason,
                "count": count,
                "recommended_action": recommended_action_for(reason),
                "share": round(count / len(pattern_lists), 4) if pattern_lists else 0,
            }
        )
    for cid, stats in top_hurt[:3]:
        if stats.get("hurt_rate", 0) > 0.35:
            priority_actions.append(
                {
                    "component_id": cid,
                    "hurt_rate": stats.get("hurt_rate"),
                    "recommended_action": f"Shadow-reduce {cid} weight when hurt_rate > 35% (no auto-apply)",
                }
            )

    store_paths = store.save_artifacts(
        comparisons_summary=comp_summary,
        blame_matrix=blame_matrix,
        pattern_summary=pattern_summary,
        failure_breakdown=failure_breakdown,
        priority_actions=priority_actions,
    )

    incorrect_n = sum(1 for c in comparisons if c.outcome == "incorrect")
    recommendation = decide_recommendation(
        comparisons_n=len(comparisons),
        incorrect_n=incorrect_n,
        pattern_summary=pattern_summary,
        live_paired=source_stats.get("live_paired", 0),
    )
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "NEEDS_MORE_DATA"

    report = {
        "generated_at": _utc_now(),
        "phase": PHASE,
        "model_version": MODEL_VERSION,
        "source_stats": source_stats,
        "comparisons": len(comparisons),
        "incorrect": incorrect_n,
        "knowledge_records": len(pattern_lists),
        "failure_breakdown": failure_breakdown,
        "pattern_summary": pattern_summary,
        "top_hurt_components": [{"component_id": c, **s} for c, s in top_hurt[:5]],
        "market_accuracy": comp_summary.get("market_accuracy"),
        "recommendation": recommendation,
        "store_paths": store_paths,
        "production_changes": False,
        "api_calls_used": 0,
    }
    (ARTIFACT_DIR / "phase58d_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_markdown(report, comp_summary, failure_breakdown, pattern_summary, priority_actions, global_blame)
    return report


def _write_markdown(
    report: dict[str, Any],
    comp_summary: dict[str, Any],
    failure_breakdown: dict[str, Any],
    pattern_summary: dict[str, Any],
    priority_actions: list[dict[str, Any]],
    global_blame: dict[str, Any],
) -> None:
    rec = report.get("recommendation")
    top_hurt = sorted(global_blame.items(), key=lambda x: x[1].get("hurt_rate", 0), reverse=True)
    top_reason = failure_breakdown.get("top_reason") or "unknown"
    market_acc = comp_summary.get("market_accuracy") or {}
    healthiest = max(market_acc.items(), key=lambda x: x[1])[0] if market_acc else "n/a"

    lines = [
        "# PHASE 58D — Root Cause Analyzer",
        "",
        f"**Date:** {_utc_now()[:10]}",
        "**Mode:** Post-Match Analysis → Failure Attribution → Knowledge Extraction",
        "**Status:** Complete — shadow only",
        "**API calls:** 0",
        "",
        f"### Final recommendation: **`{rec}`**",
        "",
        "---",
        "",
        "## Part A — Post-Match Comparison",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Comparisons analyzed | {report.get('comparisons')} |",
        f"| Incorrect predictions | {report.get('incorrect')} |",
        f"| Live 58C paired | {report.get('source_stats', {}).get('live_paired', 0)} |",
        f"| Historical replay (EGIE) | {report.get('source_stats', {}).get('historical_replay', 0)} |",
        f"| Pending 58C shadow | {report.get('source_stats', {}).get('pending_shadow', 0)} |",
        "",
        "## Part B — Failure Attribution",
        "",
        "Top failure reasons:",
        "",
    ]
    for reason, count in (failure_breakdown.get("by_reason") or {}).items():
        lines.append(f"- `{reason}`: {count}")

    lines.extend(
        [
            "",
            "## Part C — Component Blame Matrix",
            "",
            "Global hurt rates (top components):",
            "",
        ]
    )
    for cid, stats in top_hurt[:6]:
        lines.append(
            f"- `{cid}`: helped={stats.get('help_rate', 0):.1%}, hurt={stats.get('hurt_rate', 0):.1%}, n={stats.get('n', 0)}"
        )

    lines.extend(
        [
            "",
            "Store: `data/shadow/root_cause_store/component_blame_matrix.json`",
            "",
            "## Part D — Pattern Discovery",
            "",
        ]
    )
    for item in pattern_summary.get("top_patterns") or []:
        lines.append(f"- `{item['pattern']}`: {item['count']} ({item['rate']:.1%} of failures)")

    lines.extend(
        [
            "",
            "## Part E — Knowledge Extraction",
            "",
            f"Records written: `data/shadow/root_cause_store/knowledge_records.jsonl` ({report.get('knowledge_records')} rows)",
            "",
            "## Part F — Decision Questions",
            "",
            f"1. **Why do predictions fail?** Primary driver: `{top_reason}`",
            f"2. **Which component causes most errors?** `{top_hurt[0][0] if top_hurt else 'n/a'}` (hurt rate {top_hurt[0][1].get('hurt_rate', 0):.1%})" if top_hurt else "2. **Which component causes most errors?** n/a",
            f"3. **Which markets are healthiest?** `{healthiest}` (accuracy {market_acc.get(healthiest, 0):.1%})",
            "4. **Which recurring patterns exist?**",
        ]
    )
    for item in (pattern_summary.get("top_patterns") or [])[:5]:
        lines.append(f"   - `{item['pattern']}` ({item['count']} cases)")
    lines.append("5. **Which improvements should be prioritized?**")
    for act in priority_actions[:5]:
        if "failure_reason" in act:
            lines.append(f"   - {act['failure_reason']}: {act['recommended_action']}")
        else:
            lines.append(f"   - {act.get('component_id')}: {act.get('recommended_action')}")

    lines.extend(
        [
            "",
            f"### Final recommendation: **`{rec}`**",
            "",
            "---",
            "",
            "## Constraints honored",
            "",
            "- No deploy, production integration, automatic weight updates, or user-facing output",
            "- WDE and live predictions unchanged",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
