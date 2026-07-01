#!/usr/bin/env python3
"""PHASE ECSE-1E — Run exact score distribution backtest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_exact_score_backtest import run_exact_score_backtest

SUMMARY_PATH = ROOT / "artifacts" / "ecse_1e_backtest_summary.json"
REPORT_PATH = ROOT / "ECSE_1E_EXACT_SCORE_BACKTEST_REPORT.md"
ERROR_PATH = ROOT / "ECSE_1E_ERROR_ANALYSIS_REPORT.md"


def _backtest_report_md(summary: dict) -> str:
    o = summary["overall"]
    lines = [
        "# ECSE-1E — Exact Score Backtest Report",
        "",
        f"**Backtest version:** `{summary['backtest_version']}`  ",
        f"**Distribution method:** `{summary['distribution_method']}`  ",
        f"**Generated:** {summary['generated_at_utc']}  ",
        f"**Fixtures evaluated:** {summary['fixtures_evaluated']:,}",
        "",
        "## Overall ECSE Performance",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Top-1 hit rate | **{o['top1_hit_rate_pct']}%** |",
        f"| Top-3 hit rate | **{o['top3_hit_rate_pct']}%** |",
        f"| Top-5 hit rate | **{o['top5_hit_rate_pct']}%** |",
        f"| Top-10 hit rate | **{o['top10_hit_rate_pct']}%** |",
        f"| Avg prob on actual score | {o['avg_prob_actual']} |",
        f"| Avg log loss | {o['avg_log_loss']} |",
        f"| Avg Brier (multiclass) | {o['avg_brier']} |",
        "",
        "## Baselines",
        "",
        "| Baseline | Top-1 hit % | Notes |",
        "|----------|-------------|-------|",
    ]
    for b in summary["baselines"]:
        lines.append(
            f"| {b['name']} | {b.get('top1_hit_rate_pct', 'n/a')}% | "
            f"{b.get('predicted_score', b.get('rules', ''))} |"
        )
    lines.extend(["", "## Breakdown by data quality", ""])
    for k, v in summary["by_data_quality_bucket"].items():
        lines.append(f"- **{k}** (n={v['n']}): top1={v['top1_hit_rate_pct']}%, logloss={v['avg_log_loss']}")
    lines.extend(["", "## Breakdown by lambda_total", ""])
    for k, v in summary["by_lambda_total_bucket"].items():
        lines.append(f"- **{k}** (n={v['n']}): top1={v['top1_hit_rate_pct']}%, top5={v['top5_hit_rate_pct']}%")
    lines.extend(["", "## Breakdown by odds band", ""])
    for k, v in summary["by_odds_band"].items():
        lines.append(f"- **{k}** (n={v['n']}): top1={v['top1_hit_rate_pct']}%")
    lines.extend(["", "## Top leagues (by volume)", ""])
    for lg, v in list(summary["by_league_top20"].items())[:10]:
        lines.append(f"- {lg} (n={v['n']}): top1={v['top1_hit_rate_pct']}%")
    lines.extend(["", "---", "", "*Evaluation only. No training, tuning, or deployment.*"])
    return "\n".join(lines)


def _error_report_md(summary: dict) -> str:
    m = summary["miss_analysis"]
    lines = [
        "# ECSE-1E — Error Analysis Report",
        "",
        f"**Fixtures:** {summary['fixtures_evaluated']:,}",
        "",
        "## Common prediction misses (top pairs)",
        "",
        "| Predicted | Actual | Count |",
        "|-----------|--------|-------|",
    ]
    for row in m["top_predicted_actual_pairs"]:
        lines.append(f"| {row['predicted']} | {row['actual']} | {row['count']} |")
    lines.extend(
        [
            "",
            "## Specific patterns",
            "",
            f"- Predicted **1-1**, actual **2-1**: {m['predicted_1_1_actual_2_1']:,}",
            f"- Predicted **2-1**, actual **1-1**: {m['predicted_2_1_actual_1_1']:,}",
            f"- Low-score underestimation (0-0/1-0/0-1 rank>5 or p<5%): "
            f"**{m['underestimate_low_score_rate_pct']}%** of low-score results (n={m['underestimate_low_score_n']:,})",
            f"- High-score overprediction (pred 3+ goals, actual <3): "
            f"**{m['overestimate_3plus_when_actual_under_3_pct']}%** of 3+ predictions "
            f"(n={m['overestimate_3plus_predictions']:,})",
            "",
            "## Interpretation",
            "",
            "- Independent Poisson tends to concentrate mass on 1-1 / 1-2 / 2-1 corridors.",
            "- Low-scoring results (0-0, 1-0) are systematically under-weighted vs market tails.",
            "- Occasional 3+ goal top picks miss when actual totals stay low.",
            "",
            "---",
            "",
            "*Read-only evaluation against `historical_fixture_results`.*",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    print("ECSE-1E exact score backtest\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    summary = run_exact_score_backtest(conn)

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(_backtest_report_md(summary), encoding="utf-8")
    ERROR_PATH.write_text(_error_report_md(summary), encoding="utf-8")

    print(json.dumps({"overall": summary["overall"], "baselines": summary["baselines"]}, indent=2))
    print(f"\nSummary: {SUMMARY_PATH}")
    print(f"Report: {REPORT_PATH}")
    print(f"Errors: {ERROR_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
