"""
SMC Backtester
==============
Simulates SMC signals on historical OHLCV data and records trade outcomes.

For each signal the backtester walks forward bar-by-bar from the entry
and checks whether price hits the target (TP) or stop (SL) first.

Metrics Produced
----------------
- Total trades
- Win rate (%)
- Average R:R on winners
- Profit factor
- Total R gained / lost
- Equity curve (per-trade R)
- Drawdown stats
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class Trade:
    bar_idx:   int
    timestamp: Any
    pair:      str
    side:      str          # 'long' | 'short'
    entry:     float
    stop:      float
    target:    float
    risk_pips: float
    source:    str          # 'OB' | 'FVG'
    outcome:   str  = ""   # 'win' | 'loss' | 'open'
    exit_bar:  int  = -1
    exit_price: float = 0.0
    pnl_r:     float = 0.0  # P&L in units of Risk


def backtest_signals(
    df: pd.DataFrame,
    signals: list[dict],
    max_bars_open: int = 48,
) -> list[Trade]:
    """
    Walk forward and determine TP/SL outcome for each signal.

    Parameters
    ----------
    df            : full OHLCV DataFrame (same one used for signal generation)
    signals       : list of signal dicts from strategy.generate_signals
    max_bars_open : force-close a trade after this many bars if neither TP nor SL hit
    """
    trades: list[Trade] = []

    for sig in signals:
        trade = Trade(
            bar_idx   = sig["bar_idx"],
            timestamp = sig["timestamp"],
            pair      = sig["pair"],
            side      = sig["side"],
            entry     = sig["entry"],
            stop      = sig["stop"],
            target    = sig["target"],
            risk_pips = sig["risk_pips"],
            source    = sig["source"],
        )

        entry_idx = sig["bar_idx"]
        risk = abs(trade.entry - trade.stop)
        if risk == 0:
            continue

        outcome = "open"
        exit_bar = -1
        exit_price = trade.entry

        for j in range(entry_idx + 1, min(entry_idx + max_bars_open + 1, len(df))):
            bar = df.iloc[j]

            if trade.side == "long":
                if bar["low"] <= trade.stop:
                    outcome    = "loss"
                    exit_bar   = j
                    exit_price = trade.stop
                    break
                if bar["high"] >= trade.target:
                    outcome    = "win"
                    exit_bar   = j
                    exit_price = trade.target
                    break
            else:  # short
                if bar["high"] >= trade.stop:
                    outcome    = "loss"
                    exit_bar   = j
                    exit_price = trade.stop
                    break
                if bar["low"] <= trade.target:
                    outcome    = "win"
                    exit_bar   = j
                    exit_price = trade.target
                    break

        # Force-close at last bar close if still open
        if outcome == "open":
            exit_bar   = min(entry_idx + max_bars_open, len(df) - 1)
            exit_price = df["close"].iloc[exit_bar]
            if trade.side == "long":
                pnl = exit_price - trade.entry
            else:
                pnl = trade.entry - exit_price
            outcome = "win" if pnl > 0 else "loss"

        # P&L in R
        if trade.side == "long":
            pnl_r = (exit_price - trade.entry) / risk
        else:
            pnl_r = (trade.entry - exit_price) / risk

        trade.outcome    = outcome
        trade.exit_bar   = exit_bar
        trade.exit_price = round(exit_price, 6)
        trade.pnl_r      = round(pnl_r, 3)
        trades.append(trade)

    return trades


def compute_metrics(trades: list[Trade]) -> dict:
    """
    Compute aggregate performance metrics from a list of closed trades.
    """
    if not trades:
        return {}

    total    = len(trades)
    wins     = [t for t in trades if t.outcome == "win"]
    losses   = [t for t in trades if t.outcome == "loss"]
    win_rate = len(wins) / total * 100

    gross_profit = sum(t.pnl_r for t in wins)
    gross_loss   = abs(sum(t.pnl_r for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    net_r   = sum(t.pnl_r for t in trades)
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0

    # Equity curve and drawdown
    equity = np.cumsum([t.pnl_r for t in trades])
    peak   = np.maximum.accumulate(equity)
    dd     = equity - peak
    max_dd = float(dd.min())

    ob_trades  = [t for t in trades if t.source == "OB"]
    fvg_trades = [t for t in trades if t.source == "FVG"]

    return {
        "total_trades":   total,
        "wins":           len(wins),
        "losses":         len(losses),
        "win_rate_pct":   round(win_rate, 1),
        "net_r":          round(net_r, 2),
        "profit_factor":  round(profit_factor, 2),
        "avg_win_r":      round(avg_win, 2),
        "avg_loss_r":     round(avg_loss, 2),
        "max_drawdown_r": round(max_dd, 2),
        "ob_trades":      len(ob_trades),
        "fvg_trades":     len(fvg_trades),
        "ob_win_rate":    round(
            len([t for t in ob_trades if t.outcome == "win"]) / len(ob_trades) * 100, 1
        ) if ob_trades else 0.0,
        "fvg_win_rate":   round(
            len([t for t in fvg_trades if t.outcome == "win"]) / len(fvg_trades) * 100, 1
        ) if fvg_trades else 0.0,
        "equity_curve":   equity.tolist(),
    }


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    """Convert list of Trade objects to a tidy DataFrame."""
    rows = []
    for t in trades:
        rows.append({
            "pair":       t.pair,
            "timestamp":  t.timestamp,
            "side":       t.side,
            "entry":      t.entry,
            "stop":       t.stop,
            "target":     t.target,
            "exit_price": t.exit_price,
            "outcome":    t.outcome,
            "pnl_r":      t.pnl_r,
            "risk_pips":  t.risk_pips,
            "source":     t.source,
        })
    return pd.DataFrame(rows)
