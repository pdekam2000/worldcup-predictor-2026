#!/usr/bin/env python3
"""Phase 31D — run hybrid replay prototype (100-fixture sample)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.backtesting.hybrid_replay import (  # noqa: E402
    compare_with_phase31b,
    run_hybrid_replay,
)

ARTIFACTS = ROOT / "artifacts"
REPORT_PATH = ROOT / "PHASE_31D_HYBRID_REPLAY_PROTOTYPE_REPORT.md"


def _pct(rate: float | None) -> str:
    if rate is None:
        return "n/a"
    return f"{rate * 100:.1f}%"


def _write_report(hybrid: dict, comparison: dict, artifact_path: Path) -> None:
    meta = hybrid["meta"]
    h_sum = hybrid["summary"]
    b_sum = comparison["baseline_31b"]
    delta = comparison["delta"]
    missing = hybrid["missing_enrichment"]
    t60_h = h_sum["threshold_matrix"]["60"]
    t60_b = b_sum["threshold_matrix"]["60"]
    buckets_h = h_sum["confidence_bucket_analysis"]
    buckets_b = b_sum["confidence_bucket_analysis"]

    phase31e_needed = (
        delta["average_confidence"] < 5
        or t60_h.get("recommendation_rate", 0) == 0
        or meta["external_api_calls"] > 0
    )
    phase31e_rec = (
        "**Yes — Phase 31E recommended.** Hybrid replay still cannot reach production recommendation "
        "rates; a historical enrichment rebuild (Option C from Phase 31C) is required for full parity."
        if phase31e_needed
        else "**No — Phase 31E optional.** Hybrid replay achieves meaningful confidence/coverage gains "
        "with stored data alone; monitor before investing in full rebuild."
    )

    lines = [
        "# PHASE 31D — HYBRID REPLAY PROTOTYPE",
        "",
        "**Mode:** Implement → Validate → Report",
        "",
        "**No deploy. No threshold changes.**",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Phase 31B (baseline) | Phase 31D (hybrid) | Delta |",
        "|--------|---------------------:|-------------------:|------:|",
        f"| Sample fixtures | {comparison['baseline_cores_count']} | {meta['replayed_ok']} | — |",
        f"| Average confidence | **{b_sum['average_confidence']:.1f}** | **{h_sum['average_confidence']:.1f}** | **{delta['average_confidence']:+.1f}** |",
        f"| Max confidence | **{b_sum['max_confidence']:.1f}** | **{h_sum['max_confidence']:.1f}** | **{delta['max_confidence']:+.1f}** |",
        f"| Average data quality | **{b_sum['average_data_quality']:.1f}** | **{h_sum['average_data_quality']:.1f}** | **{delta['average_data_quality']:+.1f}** |",
        f"| No Bet rate @ 60 | **{_pct(t60_b.get('no_bet_rate'))}** | **{_pct(t60_h.get('no_bet_rate'))}** | **{delta['no_bet_rate_60']*100:+.1f}pp** |",
        f"| Recommendation rate @ 60 | **{_pct(t60_b.get('recommendation_rate'))}** | **{_pct(t60_h.get('recommendation_rate'))}** | **{delta['recommendation_rate_60']*100:+.1f}pp** |",
        f"| External API calls | 0 | **{meta['external_api_calls']}** | — |",
        "",
        "---",
        "",
        "## Pipeline",
        "",
        "```",
        "SQLite fixtures + results",
        "├── CacheOnlyApiFootballClient (sqlite + disk cache only)",
        "├── MatchIntelligenceBuilder.build()  [production path]",
        "├── fixture_enrichment merge + api_response_cache odds",
        "├── form injection + data quality recompute",
        "├── SpecialistOrchestrator (offline keys)",
        "└── ScoringEngine + WDE (unchanged thresholds)",
        "```",
        "",
        "---",
        "",
        "## Confidence Comparison (threshold 60)",
        "",
        f"- **31B avg confidence:** {t60_b.get('average_confidence', 0):.1f}",
        f"- **31D avg confidence:** {t60_h.get('average_confidence', 0):.1f}",
        f"- **Gain:** {delta['average_confidence']:+.1f} points",
        "",
        "## No Bet Comparison @ 60",
        "",
        f"- **31B:** {t60_b.get('no_bet_count', 0)}/{t60_b.get('total_matches', 0)} ({_pct(t60_b.get('no_bet_rate'))})",
        f"- **31D:** {t60_h.get('no_bet_count', 0)}/{t60_h.get('total_matches', 0)} ({_pct(t60_h.get('no_bet_rate'))})",
        "",
        "## Recommendation Comparison @ 55 / 60",
        "",
    ]

    for th in ("55", "60"):
        hb = h_sum["threshold_matrix"][th]
        bb = b_sum["threshold_matrix"][th]
        lines.extend(
            [
                f"### Threshold {th}",
                "",
                f"| Path | No Bet | Recommend | Avg conf |",
                f"|------|-------:|----------:|---------:|",
                f"| 31B | {_pct(bb['no_bet_rate'])} | {_pct(bb['recommendation_rate'])} | {bb['average_confidence']:.1f} |",
                f"| 31D | {_pct(hb['no_bet_rate'])} | {_pct(hb['recommendation_rate'])} | {hb['average_confidence']:.1f} |",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Confidence Distribution",
            "",
            "| Bucket | 31B count | 31D count |",
            "|--------|----------:|----------:|",
        ]
    )
    for label in buckets_h:
        lines.append(f"| {label} | {buckets_b.get(label, {}).get('count', 0)} | {buckets_h[label]['count']} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Top Missing Enrichment (31D sample)",
            "",
            "| Field | Missing count | % of sample |",
            "|-------|-------------:|------------:|",
        ]
    )
    for item in missing.get("top_missing", []):
        lines.append(f"| {item['field']} | {item['count']} | {item['pct']*100:.1f}% |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## API Call Validation",
            "",
            f"| Check | Result |",
            f"|-------|--------|",
            f"| API-Football live fetch attempts | **{meta['external_api_calls']}** |",
            f"| Sportmonks (offline keys) | **0** |",
            f"| OpenAI (offline keys) | **0** |",
            "",
            "---",
            "",
            "## Phase 31E Recommendation",
            "",
            phase31e_rec,
            "",
            "---",
            "",
            f"*Artifacts: `{artifact_path.relative_to(ROOT)}`*",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 31D hybrid replay prototype")
    parser.add_argument("--db", default=str(ROOT / "data" / "football_intelligence.db"))
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--no-specialists", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    hybrid = run_hybrid_replay(
        db_path=args.db,
        sample_size=args.sample,
        run_specialists=not args.no_specialists,
    )
    comparison = compare_with_phase31b(hybrid, db_path=args.db)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS / "phase31d_hybrid_replay_summary.json"
    payload = {
        "meta": hybrid["meta"],
        "summary": hybrid["summary"],
        "missing_enrichment": hybrid["missing_enrichment"],
        "comparison": comparison,
    }
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_report(hybrid, comparison, artifact_path)

    print(f"Hybrid replay: {hybrid['meta']['replayed_ok']}/{hybrid['meta']['sample_size']} ok")
    print(f"Avg confidence 31D: {hybrid['summary']['average_confidence']:.1f}")
    print(f"API calls blocked: {hybrid['meta']['external_api_calls']}")
    print(f"Report: {REPORT_PATH}")
    return 0 if hybrid["meta"]["external_api_calls"] == 0 and hybrid["meta"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
