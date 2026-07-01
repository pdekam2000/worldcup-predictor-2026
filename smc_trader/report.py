"""
SMC Trader — Report Generator
==============================
Generates a rich terminal report and saves an HTML/PNG report
with equity curves and trade statistics.
"""

from __future__ import annotations

import os
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False


# ─────────────────────────────────────────────
# Terminal Report
# ─────────────────────────────────────────────

def print_report(
    pair_results: dict[str, dict],
    combined: dict,
    output_dir: str = ".",
) -> None:
    """Print a formatted summary to the terminal."""

    if _RICH:
        _print_rich(pair_results, combined)
    else:
        _print_plain(pair_results, combined)

    print(f"\nCharts saved to: {os.path.abspath(output_dir)}")


def _print_rich(pair_results: dict, combined: dict) -> None:
    console = Console()

    # ── Overall Summary ──────────────────────────────────────────────
    console.rule("[bold cyan]SMC Forex Robot — Backtest Results (3 months)[/bold cyan]")
    table = Table(box=box.ROUNDED, highlight=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    rows = [
        ("Total Trades",      str(combined.get("total_trades", 0))),
        ("Win Rate",          f'{combined.get("win_rate_pct", 0):.1f}%'),
        ("Net R Gained",      f'{combined.get("net_r", 0):+.2f}R'),
        ("Profit Factor",     f'{combined.get("profit_factor", 0):.2f}'),
        ("Avg Win",           f'{combined.get("avg_win_r", 0):.2f}R'),
        ("Avg Loss",          f'{combined.get("avg_loss_r", 0):.2f}R'),
        ("Max Drawdown",      f'{combined.get("max_drawdown_r", 0):.2f}R'),
        ("OB Trades / WR",    f'{combined.get("ob_trades", 0)} / {combined.get("ob_win_rate", 0):.1f}%'),
        ("FVG Trades / WR",   f'{combined.get("fvg_trades", 0)} / {combined.get("fvg_win_rate", 0):.1f}%'),
    ]
    for r in rows:
        table.add_row(*r)
    console.print(table)

    # ── Per Pair ─────────────────────────────────────────────────────
    console.rule("[bold]Per-Pair Breakdown[/bold]")
    pt = Table(box=box.SIMPLE_HEAVY)
    pt.add_column("Pair")
    pt.add_column("Trades", justify="right")
    pt.add_column("WR %",   justify="right")
    pt.add_column("Net R",  justify="right")
    pt.add_column("PF",     justify="right")

    for pair, m in pair_results.items():
        if not m:
            continue
        wr   = m.get("win_rate_pct", 0)
        netr = m.get("net_r", 0)
        pf   = m.get("profit_factor", 0)
        color = "green" if netr > 0 else "red"
        pt.add_row(
            pair,
            str(m.get("total_trades", 0)),
            f"[{color}]{wr:.1f}%[/{color}]",
            f"[{color}]{netr:+.2f}R[/{color}]",
            f"{pf:.2f}",
        )
    console.print(pt)


def _print_plain(pair_results: dict, combined: dict) -> None:
    print("\n===== SMC Forex Robot — Backtest Results =====")
    for k, v in combined.items():
        if k != "equity_curve":
            print(f"  {k}: {v}")
    print("\n--- Per-Pair ---")
    for pair, m in pair_results.items():
        if m:
            print(f"  {pair}: WR={m.get('win_rate_pct')}% | NetR={m.get('net_r')} | PF={m.get('profit_factor')}")


# ─────────────────────────────────────────────
# Chart Generation
# ─────────────────────────────────────────────

def save_charts(
    pair_results: dict[str, dict],
    combined: dict,
    output_dir: str = ".",
) -> str:
    """
    Generate and save a multi-panel report chart.
    Returns the path to the saved image.
    """
    os.makedirs(output_dir, exist_ok=True)
    pairs = [p for p, m in pair_results.items() if m and m.get("equity_curve")]

    n_pairs = len(pairs)
    if n_pairs == 0:
        return ""

    fig = plt.figure(figsize=(18, 4 + 3 * (n_pairs + 1)))
    fig.patch.set_facecolor("#0d1117")
    gs = gridspec.GridSpec(n_pairs + 2, 2, figure=fig, hspace=0.6, wspace=0.4)

    # ── Combined equity curve ─────────────────────────────────────
    ax0 = fig.add_subplot(gs[0, :])
    ax0.set_facecolor("#161b22")
    eq = combined.get("equity_curve", [])
    if eq:
        x = np.arange(len(eq))
        ax0.plot(x, eq, color="#58a6ff", linewidth=2, label="Combined Equity (R)")
        ax0.axhline(0, color="#ffffff30", linewidth=0.8)
        ax0.fill_between(x, eq, 0, where=np.array(eq) >= 0, alpha=0.2, color="#3fb950")
        ax0.fill_between(x, eq, 0, where=np.array(eq) <  0, alpha=0.2, color="#f85149")
    ax0.set_title("Combined Equity Curve (All Pairs)", color="white", fontsize=13, pad=8)
    ax0.tick_params(colors="white")
    ax0.set_xlabel("Trade #", color="white")
    ax0.set_ylabel("R",       color="white")
    for spine in ax0.spines.values():
        spine.set_color("#30363d")

    # ── Stats bar chart ───────────────────────────────────────────
    ax1 = fig.add_subplot(gs[1, :])
    ax1.set_facecolor("#161b22")
    pair_names = [p for p in pairs]
    wrs = [pair_results[p]["win_rate_pct"] for p in pair_names]
    colors = ["#3fb950" if w >= 50 else "#f85149" for w in wrs]
    bars = ax1.bar(pair_names, wrs, color=colors, edgecolor="#30363d")
    ax1.axhline(50, color="#ffffff60", linewidth=1, linestyle="--")
    ax1.set_title("Win Rate by Pair (%)", color="white", fontsize=12)
    ax1.tick_params(colors="white")
    ax1.set_ylim(0, 100)
    for bar, wr in zip(bars, wrs):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"{wr:.0f}%",
            ha="center",
            color="white",
            fontsize=9,
        )
    for spine in ax1.spines.values():
        spine.set_color("#30363d")

    # ── Per-pair equity curves ────────────────────────────────────
    for idx, pair in enumerate(pairs):
        row = idx + 2
        ax = fig.add_subplot(gs[row, 0])
        ax.set_facecolor("#161b22")
        eq = pair_results[pair].get("equity_curve", [])
        x  = np.arange(len(eq))
        ax.plot(x, eq, color="#58a6ff", linewidth=1.5)
        ax.axhline(0, color="#ffffff30", linewidth=0.8)
        ax.fill_between(x, eq, 0, where=np.array(eq) >= 0, alpha=0.15, color="#3fb950")
        ax.fill_between(x, eq, 0, where=np.array(eq) <  0, alpha=0.15, color="#f85149")
        ax.set_title(f"{pair} Equity Curve", color="white", fontsize=10)
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("#30363d")

        # ── Per-pair stats text ──────────────────────────────────
        ax2 = fig.add_subplot(gs[row, 1])
        ax2.set_facecolor("#161b22")
        ax2.axis("off")
        m = pair_results[pair]
        stats_text = (
            f"Trades:   {m.get('total_trades', 0)}\n"
            f"Win Rate: {m.get('win_rate_pct', 0):.1f}%\n"
            f"Net R:    {m.get('net_r', 0):+.2f}\n"
            f"Profit F: {m.get('profit_factor', 0):.2f}\n"
            f"Avg Win:  {m.get('avg_win_r', 0):.2f}R\n"
            f"Max DD:   {m.get('max_drawdown_r', 0):.2f}R"
        )
        ax2.text(
            0.05, 0.5, stats_text,
            transform=ax2.transAxes,
            fontsize=11, color="white",
            verticalalignment="center",
            fontfamily="monospace",
            bbox=dict(facecolor="#0d1117", edgecolor="#30363d", boxstyle="round,pad=0.5"),
        )
        ax2.set_title(f"{pair} Stats", color="white", fontsize=10)

    fig.suptitle(
        "SMC Robot Trader — 3-Month Backtest Results",
        color="white",
        fontsize=16,
        y=0.98,
    )

    path = os.path.join(output_dir, "smc_backtest_report.png")
    plt.savefig(path, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
