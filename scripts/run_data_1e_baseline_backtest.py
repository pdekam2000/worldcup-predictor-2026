#!/usr/bin/env python3
"""PHASE DATA-1E — Run historical odds baseline ROI backtest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.historical_odds_baseline_backtest import (
    STRATEGIES,
    backup_artifact,
    run_baseline_backtest,
    summarize_state,
)

ARTIFACTS = ROOT / "artifacts"
BACKUP_DIR = ARTIFACTS / "backups"
SUMMARY_PATH = ARTIFACTS / "data_1e_backtest_summary.json"


def _baseline_report_md(summary: dict) -> str:
    ds = summary["dataset"]
    lines = [
        "# DATA-1E Baseline Backtest Report",
        "",
        f"**Generated:** {summary.get('generated_at')}",
        "",
        "## Dataset",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Join rows | {ds['join_rows']} |",
        f"| Evaluable rows | {ds['evaluable_rows']} |",
        f"| Unevaluable rows | {ds['unevaluable_rows']} |",
        f"| Expected join rows (DATA-1D) | {ds['expected_join_rows']} |",
        "",
        "## Strategy ROI summary",
        "",
        "| Strategy | Bets | Hit rate % | Avg odds | ROI % | Profit |",
        "|----------|------|------------|----------|-------|--------|",
    ]
    for name in STRATEGIES:
        m = summary["strategies"].get(name, {})
        lines.append(
            f"| {name} | {m.get('bets', 0)} | {m.get('hit_rate_pct')} | "
            f"{m.get('avg_odds')} | {m.get('roi_pct')} | {m.get('profit')} |"
        )

    ovc = summary.get("opening_vs_closing", {})
    lines.extend(
        [
            "",
            "## Opening vs closing (strategy G)",
            "",
            f"- Opening ROI %: {ovc.get('opening', {}).get('roi_pct')}",
            f"- Closing ROI %: {ovc.get('closing', {}).get('roi_pct')}",
            f"- Delta (closing - opening) ROI %: {ovc.get('delta_roi_pct')}",
            "",
            "## Notes",
            "",
            "- Research-only baseline; not production predictions.",
            "- Stake = 1 unit per bet; ROI = (returns - stakes) / stakes × 100.",
            "- Default odds: closing with opening fallback (except F/G variants).",
            "- No API calls; no WDE/EGIE/ECSE changes.",
            "",
        ]
    )
    return "\n".join(lines)


def _market_roi_md(summary: dict) -> str:
    lines = [
        "# DATA-1E Market ROI Tables",
        "",
        "## By market (strategy A — all selections)",
        "",
        "| Market | Bets | Hit % | Avg odds | ROI % |",
        "|--------|------|-------|----------|-------|",
    ]
    by_market = summary.get("by_market", {})
    for market, strategies in sorted(by_market.items()):
        m = strategies.get("A_all_selections", {})
        lines.append(
            f"| {market} | {m.get('bets', 0)} | {m.get('hit_rate_pct')} | "
            f"{m.get('avg_odds')} | {m.get('roi_pct')} |"
        )

    lines.extend(
        [
            "",
            "## By market (strategy E — top odds per fixture/market)",
            "",
            "| Market | Bets | Hit % | Avg odds | ROI % |",
            "|--------|------|-------|----------|-------|",
        ]
    )
    for market, strategies in sorted(by_market.items()):
        m = strategies.get("E_top_odds_per_fixture_market", {})
        if m.get("bets", 0) == 0:
            continue
        lines.append(
            f"| {market} | {m.get('bets', 0)} | {m.get('hit_rate_pct')} | "
            f"{m.get('avg_odds')} | {m.get('roi_pct')} |"
        )

    lines.extend(
        [
            "",
            "## By odds band (strategy A)",
            "",
            "| Odds band | Bets | Hit % | ROI % |",
            "|-----------|------|-------|-------|",
        ]
    )
    for band, strategies in sorted(summary.get("by_odds_band", {}).items()):
        m = strategies.get("A_all_selections", {})
        lines.append(
            f"| {band} | {m.get('bets', 0)} | {m.get('hit_rate_pct')} | {m.get('roi_pct')} |"
        )

    lines.extend(
        [
            "",
            "## Top leagues (strategy A, top 20)",
            "",
            "| League | Bets | Hit % | ROI % |",
            "|--------|------|-------|-------|",
        ]
    )
    for league, strategies in summary.get("by_league_top20", {}).items():
        m = strategies.get("A_all_selections", {})
        lines.append(
            f"| {league} | {m.get('bets', 0)} | {m.get('hit_rate_pct')} | {m.get('roi_pct')} |"
        )

    lines.extend(
        [
            "",
            "## By season (strategy A)",
            "",
            "| Season | Bets | Hit % | ROI % |",
            "|--------|------|-------|-------|",
        ]
    )
    for season, strategies in sorted(summary.get("by_season", {}).items()):
        m = strategies.get("A_all_selections", {})
        lines.append(
            f"| {season} | {m.get('bets', 0)} | {m.get('hit_rate_pct')} | {m.get('roi_pct')} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="DATA-1E baseline backtest")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    conn = connect(get_db_path(args.db or settings.sqlite_path))

    backup_artifact(SUMMARY_PATH, BACKUP_DIR)

    print("Running baseline backtest (streaming join)...")
    state = run_baseline_backtest(conn)
    summary = summarize_state(state)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (ROOT / "DATA_1E_BASELINE_BACKTEST_REPORT.md").write_text(_baseline_report_md(summary), encoding="utf-8")
    (ROOT / "DATA_1E_MARKET_ROI_TABLES.md").write_text(_market_roi_md(summary), encoding="utf-8")

    ds = summary["dataset"]
    primary = summary["strategies"]["A_all_selections"]
    print("\n=== DATA-1E BASELINE BACKTEST ===")
    print(f"Join rows: {ds['join_rows']} | Evaluable: {ds['evaluable_rows']}")
    print(f"Strategy A — bets: {primary['bets']} | ROI: {primary['roi_pct']}% | Hit: {primary['hit_rate_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
