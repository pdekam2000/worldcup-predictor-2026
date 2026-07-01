#!/usr/bin/env python3
"""PHASE DATA-1F — Positive ROI forensics (read-only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.historical_odds_roi_forensics import (
    _heatmap_md,
    run_forensics,
    summarize_forensics,
)

ARTIFACTS = ROOT / "artifacts"


def _forensics_report_md(summary: dict, state) -> str:
    c = summary["strategy_c_odds_gte_3_5"]
    d = summary["strategy_d_odds_3_5_to_12"]
    bias = summary["bias_audit"]
    var = summary["variance"]
    stab = summary["stability_split"]

    lines = [
        "# DATA-1F ROI Forensics Report",
        "",
        f"**Generated:** {summary['generated_at']}",
        "",
        "## Executive finding",
        "",
        bias.get("interpretation", ""),
        "",
        f"- Strategy C bets: **{c['bets']}** | ROI **{c['roi_pct']}%** | 95% CI **[{c['roi_ci95_low']}%, {c['roi_ci95_high']}%]**",
        f"- Strategy D bets: **{d['bets']}** | ROI **{d['roi_pct']}%** | 95% CI **[{d['roi_ci95_low']}%, {d['roi_ci95_high']}%]**",
        f"- Small-sample warning: **{bias.get('small_sample_warning')}** (<5,000 bets)",
        "",
        "## Why positive ROI appears",
        "",
        "1. **Tiny longshot slice** — only ~0.17% of join rows have closing odds ≥3.5.",
        "2. **Wide confidence intervals** — true ROI likely spans negative and positive at this N.",
        "3. **Segment concentration** — profit may cluster in a few leagues/markets with low N.",
        "4. **Survivorship** — exports are settled matches only; no cancelled/postponed longshots in band.",
        "5. **Single bookmaker** — Bet365 only; no cross-book arbitrage signal.",
        "",
        "## Variance & drawdown",
        "",
        f"| Metric | Strategy C | Strategy D |",
        f"|--------|------------|------------|",
        f"| Std profit/bet | {var.get('c_std_per_bet')} | {var.get('d_std_per_bet')} |",
        f"| Max drawdown (units) | {var.get('strategy_c_max_drawdown_units')} | {var.get('strategy_d_max_drawdown_units')} |",
        f"| ROI 95% CI | {var.get('c_expected_roi_range_ci95')} | {var.get('d_expected_roi_range_ci95')} |",
        "",
        "## Temporal stability (strategy C)",
        "",
        f"- Split month: `{stab.get('split_month')}`",
        f"- First half ROI: {stab.get('first_half_c', {}).get('roi_pct')}% ({stab.get('first_half_c', {}).get('bets')} bets)",
        f"- Second half ROI: {stab.get('second_half_c', {}).get('roi_pct')}% ({stab.get('second_half_c', {}).get('bets')} bets)",
        "",
        "## Bias & integrity audit",
        "",
        f"| Check | Result |",
        f"|-------|--------|",
        f"| Survivorship | {bias.get('survivorship')} |",
        f"| Closing timestamp after kickoff (+2h) | {bias.get('data_leakage_closing_after_kickoff')} / {bias.get('leakage_rows_checked')} checked |",
        f"| Duplicate settlement groups (same fixture/market/selection/odds) | {bias.get('duplicate_settlement_groups')} |",
        f"| Invalid odds rows skipped | {bias.get('invalid_odds_rows')} |",
        "",
        "## ROI by odds band (strategy C)",
        "",
        "| Band | Bets | Hit % | ROI % | CI low | CI high |",
        "|------|------|-------|-------|--------|---------|",
    ]
    for band, m in sorted(summary.get("by_odds_band_c", {}).items()):
        lines.append(
            f"| {band} | {m['bets']} | {m['hit_rate_pct']} | {m['roi_pct']} | {m['roi_ci95_low']} | {m['roi_ci95_high']} |"
        )

    lines.extend(
        [
            "",
            "## ROI by selection side (strategy C)",
            "",
            "| Side | Bets | ROI % |",
            "|------|------|-------|",
        ]
    )
    for side, m in sorted(summary.get("by_side_c", {}).items(), key=lambda x: -(x[1].get("bets") or 0)):
        lines.append(f"| {side} | {m['bets']} | {m['roi_pct']} |")

    lines.extend(
        [
            "",
            "## ROI by month (strategy C)",
            "",
            "| Month | Bets | ROI % |",
            "|-------|------|-------|",
        ]
    )
    for month, m in sorted(summary.get("by_month_c", {}).items()):
        lines.append(f"| {month} | {m['bets']} | {m['roi_pct']} |")

    lines.extend(_heatmap_md(state.heatmap_c, "ROI heatmap — Strategy C (market × league, top leagues)"))
    lines.extend(_heatmap_md(state.heatmap_d, "ROI heatmap — Strategy D (market × league)"))

    lines.extend(
        [
            "## Stable profitable segments (C, CI entirely >0, n≥30)",
            "",
        ]
    )
    stable = summary.get("stable_profitable_c") or []
    if stable:
        for s in stable[:10]:
            lines.append(
                f"- **{s['segment']}**: ROI {s['roi_pct']}% ({s['bets']} bets, CI {s['roi_ci95_low']}–{s['roi_ci95_high']})"
            )
    else:
        lines.append("- *None* — no league segment has 95% CI fully above zero with n≥30.")

    lines.extend(["", "## Unstable / low-N segments", ""])
    for s in (summary.get("unstable_segments_c") or [])[:10]:
        lines.append(f"- {s['segment']}: {s['bets']} bets, ROI {s.get('roi_pct')}%")

    lines.append("")
    return "\n".join(lines)


def _league_rankings_md(summary: dict, strategy_key: str, title: str) -> str:
    rankings = summary["rankings"][strategy_key]
    lines = [f"# {title}", ""]
    lines.append("## Top leagues (min 15 bets)")
    lines.append("")
    lines.append("| Rank | League | Bets | Hit % | ROI % | CI 95% |")
    lines.append("|------|--------|------|-------|-------|--------|")
    for i, row in enumerate(rankings.get("top", []), 1):
        lines.append(
            f"| {i} | {row['segment']} | {row['bets']} | {row['hit_rate_pct']} | "
            f"{row['roi_pct']} | {row['roi_ci95_low']} – {row['roi_ci95_high']} |"
        )
    lines.extend(["", "## Worst leagues", ""])
    lines.append("| Rank | League | Bets | Hit % | ROI % |")
    lines.append("|------|--------|------|-------|-------|")
    for i, row in enumerate(rankings.get("worst", []), 1):
        lines.append(
            f"| {i} | {row['segment']} | {row['bets']} | {row['hit_rate_pct']} | {row['roi_pct']} |"
        )
    return "\n".join(lines) + "\n"


def _market_rankings_md(summary: dict) -> str:
    lines = [
        "# DATA-1F Market Rankings",
        "",
        "## Strategy C (odds ≥ 3.5)",
        "",
        "| Market | Bets | Hit % | Avg odds | ROI % | CI 95% |",
        "|--------|------|-------|----------|-------|--------|",
    ]
    for market, m in sorted(
        summary.get("by_market_c", {}).items(),
        key=lambda x: x[1].get("roi_pct") or -999,
        reverse=True,
    ):
        lines.append(
            f"| {market} | {m['bets']} | {m['hit_rate_pct']} | {m['avg_odds']} | "
            f"{m['roi_pct']} | {m['roi_ci95_low']} – {m['roi_ci95_high']} |"
        )
    lines.extend(
        [
            "",
            "## Strategy D (odds 3.5–12.0)",
            "",
            "| Market | Bets | Hit % | Avg odds | ROI % | CI 95% |",
            "|--------|------|-------|----------|-------|--------|",
        ]
    )
    for market, m in sorted(
        summary.get("by_market_d", {}).items(),
        key=lambda x: x[1].get("roi_pct") or -999,
        reverse=True,
    ):
        lines.append(
            f"| {market} | {m['bets']} | {m['hit_rate_pct']} | {m['avg_odds']} | "
            f"{m['roi_pct']} | {m['roi_ci95_low']} – {m['roi_ci95_high']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    print("Running ROI forensics (read-only)...")
    state = run_forensics(conn)
    summary = summarize_forensics(state)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "data_1f_forensics_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (ROOT / "DATA_1F_ROI_FORENSICS_REPORT.md").write_text(_forensics_report_md(summary, state), encoding="utf-8")
    (ROOT / "DATA_1F_LEAGUE_RANKINGS.md").write_text(
        _league_rankings_md(summary, "league_c", "DATA-1F League Rankings (Strategy C)")
        + "\n"
        + _league_rankings_md(summary, "league_d", "Strategy D"),
        encoding="utf-8",
    )
    (ROOT / "DATA_1F_MARKET_RANKINGS.md").write_text(_market_rankings_md(summary), encoding="utf-8")

    c = summary["strategy_c_odds_gte_3_5"]
    print(f"\n=== DATA-1F FORENSICS ===")
    print(f"Strategy C: {c['bets']} bets | ROI {c['roi_pct']}% | CI [{c['roi_ci95_low']}, {c['roi_ci95_high']}]")
    print(f"Stable profitable leagues (CI>0): {len(summary.get('stable_profitable_c') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
