"""
SMC Robot Trader — Main Backtest Runner
=========================================
Usage:
    python smc_trader/run_backtest.py

Options (edit CONFIG below or pass CLI flags):
    --pairs    EURUSD GBPUSD USDJPY ...
    --tf       H1 | H4 | D1
    --months   3  (how many months of history)
    --rr       2.0  (reward-to-risk ratio)
    --output   ./smc_results
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Allow running from any cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smc_trader.data_feed   import fetch_all_pairs, POPULAR_PAIRS
from smc_trader.smc_engine  import run_smc_pipeline
from smc_trader.strategy    import generate_signals
from smc_trader.backtester  import backtest_signals, compute_metrics, trades_to_dataframe
from smc_trader.report      import print_report, save_charts


# ── Default Configuration ─────────────────────────────────────────────────
CONFIG = {
    "pairs":   ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "GBPJPY", "XAUUSD"],
    "tf":      "H1",
    "months":  3,
    "rr":      2.0,
    "swing_window": 5,
    "ob_lookback":  5,
    "confirmation_bars": 5,
    "max_bars_open": 48,
    "output":  "smc_results",
}


def parse_args() -> dict:
    p = argparse.ArgumentParser(description="SMC Forex Robot Backtester")
    p.add_argument("--pairs",  nargs="+", default=CONFIG["pairs"])
    p.add_argument("--tf",     default=CONFIG["tf"])
    p.add_argument("--months", type=int, default=CONFIG["months"])
    p.add_argument("--rr",     type=float, default=CONFIG["rr"])
    p.add_argument("--output", default=CONFIG["output"])
    args = p.parse_args()
    return {
        "pairs":  args.pairs,
        "tf":     args.tf,
        "months": args.months,
        "rr":     args.rr,
        "output": args.output,
        **{k: v for k, v in CONFIG.items() if k not in ("pairs", "tf", "months", "rr", "output")},
    }


def run(cfg: dict) -> None:
    output_dir = cfg["output"]
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  SMC Robot Trader — Backtest")
    print(f"  Pairs  : {', '.join(cfg['pairs'])}")
    print(f"  TF     : {cfg['tf']}")
    print(f"  Period : Last {cfg['months']} months")
    print(f"  R:R    : 1:{cfg['rr']}")
    print(f"{'='*60}\n")

    # ── 1. Fetch data ─────────────────────────────────────────────
    print("[1/4] Downloading OHLCV data...")
    data = fetch_all_pairs(
        timeframe=cfg["tf"],
        months=cfg["months"],
        pairs=cfg["pairs"],
    )

    all_trades   = []
    pair_results = {}

    # ── 2. Run SMC pipeline + generate signals per pair ──────────
    print("\n[2/4] Running SMC pipeline and generating signals...")
    for pair, df in data.items():
        print(f"\n  ── {pair} ({len(df)} bars) ──")

        enriched, bull_obs, bear_obs, bull_fvgs, bear_fvgs = run_smc_pipeline(
            df,
            swing_window=cfg["swing_window"],
            ob_lookback=cfg["ob_lookback"],
        )

        signals = generate_signals(
            enriched,
            bull_obs=bull_obs,
            bear_obs=bear_obs,
            bull_fvgs=bull_fvgs,
            bear_fvgs=bear_fvgs,
            pair=pair,
            rr_ratio=cfg["rr"],
            confirmation_bars=cfg["confirmation_bars"],
        )
        print(f"     Signals found : {len(signals)}")

        # ── 3. Backtest ───────────────────────────────────────────
        trades = backtest_signals(
            enriched,
            signals,
            max_bars_open=cfg["max_bars_open"],
        )
        print(f"     Trades closed : {len(trades)}")

        metrics = compute_metrics(trades)
        pair_results[pair] = metrics
        all_trades.extend(trades)

        if metrics:
            print(
                f"     WR={metrics['win_rate_pct']}%  "
                f"NetR={metrics['net_r']:+.2f}  "
                f"PF={metrics['profit_factor']}"
            )

    # ── 4. Aggregate metrics ──────────────────────────────────────
    print("\n[3/4] Computing combined metrics...")
    combined_metrics = compute_metrics(all_trades)

    # ── 5. Report ─────────────────────────────────────────────────
    print("\n[4/4] Generating report...\n")
    print_report(pair_results, combined_metrics, output_dir=output_dir)

    chart_path = save_charts(pair_results, combined_metrics, output_dir=output_dir)
    if chart_path:
        print(f"\nChart: {chart_path}")

    # Save full trade log as CSV
    if all_trades:
        trades_df = trades_to_dataframe(all_trades)
        csv_path  = os.path.join(output_dir, "trade_log.csv")
        trades_df.to_csv(csv_path, index=False)
        print(f"Trade log: {csv_path}")

    # Save JSON metrics
    metrics_path = os.path.join(output_dir, "metrics.json")
    exportable   = {
        "combined": {k: v for k, v in combined_metrics.items() if k != "equity_curve"},
        "pairs":    {
            p: {k: v for k, v in m.items() if k != "equity_curve"}
            for p, m in pair_results.items()
            if m
        },
    }
    with open(metrics_path, "w") as f:
        json.dump(exportable, f, indent=2)
    print(f"Metrics JSON: {metrics_path}")

    print("\nDone.\n")


if __name__ == "__main__":
    cfg = parse_args()
    run(cfg)
