#!/usr/bin/env python3
"""PHASE ECSE-X2-M1 — Build M1 BTTS×OU filter and run comparison backtest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m1.backtest import run_m1_comparison_backtest
from worldcup_predictor.research.ecse_x2_m1.build import (
    audit_ecse_score_distributions_m1,
    baseline_table_row_count,
    build_ecse_score_distributions_m1,
)

SUMMARY_PATH = ROOT / "artifacts" / "ecse_x2_m1_summary.json"
FILTER_REPORT_PATH = ROOT / "ECSE_X2_M1_BTTS_OU_FILTER_REPORT.md"
BACKTEST_REPORT_PATH = ROOT / "ECSE_X2_M1_BACKTEST_REPORT.md"


def _filter_report_md(build_stats: dict, audit: dict, baseline_rows_before: int) -> str:
    return "\n".join(
        [
            "# ECSE-X2-M1 — BTTS × OU Exact Score Grid Filter",
            "",
            "**Phase:** ECSE-X2-M1  ",
            f"**Method:** `{build_stats.get('method_version')}`  ",
            f"**Output table:** `{build_stats.get('table')}`  ",
            "",
            "## Hypothesis",
            "",
            "BTTS and Over/Under 2.5 define four score-worlds that can re-rank ECSE exact-score grids:",
            "",
            "1. **yes_over** — BTTS Yes + Over 2.5 (e.g. 2-1, 1-2, 2-2, 3-1)",
            "2. **yes_under** — BTTS Yes + Under 2.5 (1-1)",
            "3. **no_under** — BTTS No + Under 2.5 (0-0, 1-0, 0-1, 2-0)",
            "4. **no_over** — BTTS No + Over 2.5 (3-0, 0-3, 4-0, 0-4)",
            "",
            "## Build Summary",
            "",
            f"- Fixtures built: **{build_stats.get('fixtures_built', 0):,}**",
            f"- Rows inserted: **{build_stats.get('distribution_rows_inserted', 0):,}**",
            f"- Skipped (idempotent): **{build_stats.get('fixtures_skipped_existing', 0):,}**",
            f"- Missing market (passthrough): **{build_stats.get('fixtures_missing_market', 0):,}**",
            f"- Baseline rows unchanged: **{baseline_rows_before:,}**",
            "",
            "## M1 Table Audit",
            "",
            f"- Rows: **{audit.get('rows', 0):,}**",
            f"- Fixtures: **{audit.get('fixtures', 0):,}**",
            f"- Prob sum violations: **{audit.get('fixtures_prob_sum_off', 0)}**",
            "",
            "### Dominant quadrant distribution",
            "",
        ]
        + [
            f"- **{k}**: {v:,}"
            for k, v in sorted((audit.get("by_dominant_quadrant") or {}).items())
        ]
        + [
            "",
            "## Safety",
            "",
            "- `ecse_score_distributions` baseline untouched",
            "- No actual results used during re-ranking",
            "- Prematch odds / λ inference only",
            "- Research/internal only",
            "",
        ]
    )


def _backtest_report_md(payload: dict) -> str:
    b = payload["baseline"]["overall"]
    m = payload["m1"]["overall"]
    d = payload["comparison"]["delta"]
    st = payload["success_threshold"]
    sp = payload["special_yes_under_quadrant"]
    lines = [
        "# ECSE-X2-M1 — Backtest Comparison Report",
        "",
        f"**Fixtures evaluated:** {payload['baseline']['fixtures_evaluated']:,}  ",
        f"**Success threshold passed:** {'YES' if st['passed'] else 'NO'}  ",
        "",
        "## Overall — Baseline vs M1",
        "",
        "| Metric | Baseline | M1 | Delta (M1 − Baseline) |",
        "|--------|----------|-----|------------------------|",
        f"| Top-1 hit % | {b['top1_hit_rate_pct']} | {m['top1_hit_rate_pct']} | **{d['top1_hit_rate_pct']:+.4f}** |",
        f"| Top-3 hit % | {b['top3_hit_rate_pct']} | {m['top3_hit_rate_pct']} | **{d['top3_hit_rate_pct']:+.4f}** |",
        f"| Top-5 hit % | {b['top5_hit_rate_pct']} | {m['top5_hit_rate_pct']} | **{d['top5_hit_rate_pct']:+.4f}** |",
        f"| Top-10 hit % | {b['top10_hit_rate_pct']} | {m['top10_hit_rate_pct']} | **{d['top10_hit_rate_pct']:+.4f}** |",
        f"| Avg prob actual | {b['avg_prob_actual']} | {m['avg_prob_actual']} | {d['avg_prob_actual']:+.6f} |",
        f"| Avg log loss | {b['avg_log_loss']} | {m['avg_log_loss']} | {d['avg_log_loss']:+.6f} |",
        f"| Avg Brier | {b['avg_brier']} | {m['avg_brier']} | {d['avg_brier']:+.6f} |",
        "",
        "## Success Criteria",
        "",
        f"- Top-1 ≥ +0.5pp: `{st['top1_delta_pp']:+.4f}`",
        f"- Top-3 ≥ +1.0pp: `{st['top3_delta_pp']:+.4f}`",
        f"- Log loss improved: `{st['log_loss_delta']:+.6f}`",
        f"- Met: `{', '.join(st['criteria_met']) or 'none'}`",
        "",
        "## Special Test — High BTTS Yes + High Under 2.5",
        "",
        f"- Criteria: `{sp['criteria']}`",
        f"- Fixtures: **{sp['fixtures']:,}**",
        f"- Actual 1-1 hit rate: **{sp['actual_1_1_hit_rate_pct']}%** ({sp['actual_1_1_hits']} hits)",
        f"- 1-1 avg rank baseline → M1: **{sp['baseline_1_1_avg_rank_when_actual']} → {sp['m1_1_1_avg_rank_when_actual']}**",
        f"- 1-1 top-1 when actual baseline/M1: **{sp['baseline_1_1_top1_when_actual']} / {sp['m1_1_1_top1_when_actual']}**",
        "",
        "## Rank shifts (actual score rank)",
        "",
        f"- Improved: **{payload['rank_shift']['improved']:,}**",
        f"- Worsened: **{payload['rank_shift']['worsened']:,}**",
        f"- Unchanged: **{payload['rank_shift']['unchanged']:,}**",
        "",
        "## By dominant quadrant (M1)",
        "",
    ]
    for quad, stats in payload.get("by_quadrant", {}).items():
        lines.append(
            f"- **{quad}** (n={stats.get('n', 0):,}): "
            f"top1={stats.get('top1_hit_rate_pct')}%, logloss={stats.get('avg_log_loss')}"
        )
    lines.extend(["", "## By confidence bucket (M1)", ""])
    for bucket, stats in payload.get("by_confidence_bucket", {}).items():
        lines.append(
            f"- **{bucket}** (n={stats.get('n', 0):,}): top3={stats.get('top3_hit_rate_pct')}%"
        )
    lines.extend(["", "## Top leagues (baseline)", ""])
    for lg, stats in list(payload["baseline"].get("by_league_top20", {}).items())[:8]:
        m1_lg = payload["m1"].get("by_league_top20", {}).get(lg, {})
        lines.append(
            f"- {lg}: baseline top1={stats.get('top1_hit_rate_pct')}% → "
            f"M1={m1_lg.get('top1_hit_rate_pct', 'n/a')}%"
        )
    lines.extend(["", "---", "", "*Research only. No retraining, deployment, or API calls.*"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-X2-M1 BTTS×OU M1 filter")
    parser.add_argument("--rebuild", action="store_true", help="Delete and rebuild M1 table")
    parser.add_argument("--dry-run", action="store_true", help="Build without writes")
    parser.add_argument("--skip-build", action="store_true", help="Backtest only")
    parser.add_argument("--limit", type=int, default=None, help="Limit fixtures for test builds")
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        baseline_before = baseline_table_row_count(conn)
        if not args.skip_build:
            build_stats = build_ecse_score_distributions_m1(
                conn,
                dry_run=args.dry_run,
                rebuild=args.rebuild,
                limit=args.limit,
            )
        else:
            build_stats = {"skipped": True}
        baseline_after = baseline_table_row_count(conn)
        audit = audit_ecse_score_distributions_m1(conn)
        backtest = run_m1_comparison_backtest(conn)
    finally:
        conn.close()

    if baseline_before != baseline_after:
        print("ERROR: baseline table row count changed", file=sys.stderr)
        return 2

    build_dict = build_stats.to_dict() if hasattr(build_stats, "to_dict") else build_stats
    summary = {
        "phase": "ECSE-X2-M1",
        "build": build_dict,
        "audit": audit,
        "baseline_rows_unchanged": baseline_before,
        "backtest": backtest,
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    FILTER_REPORT_PATH.write_text(_filter_report_md(build_dict, audit, baseline_before), encoding="utf-8")
    BACKTEST_REPORT_PATH.write_text(_backtest_report_md(backtest), encoding="utf-8")

    print(json.dumps({"build": build_dict, "audit": audit, "success": backtest["success_threshold"]}, indent=2))
    print(f"\nWrote {SUMMARY_PATH}")
    print(f"Wrote {FILTER_REPORT_PATH}")
    print(f"Wrote {BACKTEST_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
