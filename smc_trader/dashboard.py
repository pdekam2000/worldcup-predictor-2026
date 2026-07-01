"""
SMC Robot Trader — Streamlit Dashboard
========================================
Run with:
    streamlit run smc_trader/dashboard.py

Shows live backtest results, equity curves, trade log, and SMC metrics.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smc_trader.data_feed  import fetch_all_pairs, POPULAR_PAIRS
from smc_trader.smc_engine import run_smc_pipeline
from smc_trader.strategy   import generate_signals
from smc_trader.backtester import backtest_signals, compute_metrics, trades_to_dataframe


# ──────────────────────────────────────────────
# Page Config
# ──────────────────────────────────────────────

st.set_page_config(
    page_title="SMC Robot Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    .metric-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Sidebar — Settings
# ──────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ SMC Robot Settings")
    st.markdown("---")

    all_pairs = list(POPULAR_PAIRS.keys())
    selected_pairs = st.multiselect(
        "Pairs to backtest",
        options=all_pairs,
        default=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
    )

    timeframe = st.selectbox("Timeframe", ["H1", "H4", "D1"], index=0)
    months    = st.slider("Months of history", 1, 6, 3)
    rr_ratio  = st.slider("Risk:Reward Ratio", 1.5, 4.0, 2.0, 0.5)

    st.markdown("---")
    st.markdown("**SMC Parameters**")
    swing_window       = st.slider("Swing Window",          3, 10, 5)
    ob_lookback        = st.slider("OB Lookback (bars)",    3, 10, 5)
    confirmation_bars  = st.slider("Confirmation Bars",     2, 10, 5)
    max_bars_open      = st.slider("Max Bars Open",        12, 96, 48)

    run_btn = st.button("🚀 Run Backtest", type="primary", use_container_width=True)

st.title("📈 SMC Robot Trader — Live Backtest Dashboard")
st.caption("Smart Money Concepts | Liquidity Sweeps · Order Blocks · Fair Value Gaps")


# ──────────────────────────────────────────────
# Run Backtest
# ──────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=600)
def run_backtest(pairs, tf, months, rr, sw, ob, cb, mbo):
    data = fetch_all_pairs(timeframe=tf, months=months, pairs=pairs)
    all_trades   = []
    pair_results = {}

    for pair, df in data.items():
        enriched, bull_obs, bear_obs, bull_fvgs, bear_fvgs = run_smc_pipeline(
            df, swing_window=sw, ob_lookback=ob
        )
        signals = generate_signals(
            enriched,
            bull_obs=bull_obs, bear_obs=bear_obs,
            bull_fvgs=bull_fvgs, bear_fvgs=bear_fvgs,
            pair=pair, rr_ratio=rr, confirmation_bars=cb,
        )
        trades   = backtest_signals(enriched, signals, max_bars_open=mbo)
        metrics  = compute_metrics(trades)
        pair_results[pair] = (metrics, trades)
        all_trades.extend(trades)

    combined = compute_metrics(all_trades)
    return pair_results, combined, trades_to_dataframe(all_trades)


if run_btn or "bt_results" not in st.session_state:
    if not selected_pairs:
        st.warning("Please select at least one pair.")
        st.stop()

    with st.spinner("Running SMC backtest..."):
        pair_results, combined, trades_df = run_backtest(
            tuple(selected_pairs), timeframe, months, rr_ratio,
            swing_window, ob_lookback, confirmation_bars, max_bars_open,
        )
    st.session_state["bt_results"]   = (pair_results, combined, trades_df)

pair_results, combined, trades_df = st.session_state["bt_results"]


# ──────────────────────────────────────────────
# Top Metrics Row
# ──────────────────────────────────────────────

st.markdown("### Overall Performance")
c1, c2, c3, c4, c5, c6 = st.columns(6)

def metric_color(val, good_above=0):
    return "normal" if val > good_above else "inverse"

c1.metric("Total Trades",  combined.get("total_trades", 0))
c2.metric("Win Rate",      f'{combined.get("win_rate_pct", 0):.1f}%',
          delta=f'{combined.get("win_rate_pct", 0) - 50:.1f}% vs 50%')
c3.metric("Net R",         f'{combined.get("net_r", 0):+.2f}R')
c4.metric("Profit Factor", f'{combined.get("profit_factor", 0):.2f}')
c5.metric("Max Drawdown",  f'{combined.get("max_drawdown_r", 0):.2f}R')
c6.metric("OB / FVG WR",
          f'{combined.get("ob_win_rate", 0):.0f}% / {combined.get("fvg_win_rate", 0):.0f}%')


# ──────────────────────────────────────────────
# Combined Equity Curve
# ──────────────────────────────────────────────

st.markdown("---")
st.markdown("### Combined Equity Curve")
eq = combined.get("equity_curve", [])

if eq:
    fig_eq = go.Figure()
    x = list(range(len(eq)))
    fig_eq.add_trace(go.Scatter(
        x=x, y=eq,
        mode="lines",
        name="Equity (R)",
        line=dict(color="#58a6ff", width=2),
        fill="tozeroy",
        fillcolor="rgba(88,166,255,0.1)",
    ))
    fig_eq.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_dash="dash")
    fig_eq.update_layout(
        template="plotly_dark",
        height=300,
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title="Trade #",
        yaxis_title="R",
    )
    st.plotly_chart(fig_eq, use_container_width=True)


# ──────────────────────────────────────────────
# Per-Pair Results
# ──────────────────────────────────────────────

st.markdown("---")
st.markdown("### Per-Pair Breakdown")

pair_cols = st.columns(min(len(pair_results), 4))

for col_idx, (pair, (metrics, trades)) in enumerate(pair_results.items()):
    with pair_cols[col_idx % len(pair_cols)]:
        if not metrics:
            st.info(f"{pair}: No trades")
            continue

        wr  = metrics.get("win_rate_pct", 0)
        net = metrics.get("net_r", 0)
        pf  = metrics.get("profit_factor", 0)
        tot = metrics.get("total_trades", 0)

        color = "#3fb950" if net > 0 else "#f85149"
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:8px">
            <h4 style="color:white;margin:0">{pair}</h4>
            <p style="color:{color};font-size:1.2em;margin:4px 0">{net:+.2f}R</p>
            <small style="color:#8b949e">
                {tot} trades &nbsp;|&nbsp; WR: {wr:.0f}% &nbsp;|&nbsp; PF: {pf:.2f}
            </small>
        </div>
        """, unsafe_allow_html=True)

        # mini equity
        eq_p = metrics.get("equity_curve", [])
        if eq_p:
            fig_mini = go.Figure()
            fig_mini.add_trace(go.Scatter(
                x=list(range(len(eq_p))),
                y=eq_p,
                mode="lines",
                line=dict(color=color, width=1.5),
                fill="tozeroy",
                fillcolor=f"rgba(63,185,80,0.1)" if net > 0 else "rgba(248,81,73,0.1)",
                showlegend=False,
            ))
            fig_mini.add_hline(y=0, line_color="rgba(255,255,255,0.2)")
            fig_mini.update_layout(
                template="plotly_dark",
                height=120,
                margin=dict(l=10, r=10, t=5, b=10),
                xaxis=dict(visible=False),
                yaxis=dict(visible=True, title="R"),
            )
            st.plotly_chart(fig_mini, use_container_width=True)


# ──────────────────────────────────────────────
# Trade Log
# ──────────────────────────────────────────────

st.markdown("---")
st.markdown("### Trade Log")

if not trades_df.empty:
    display_df = trades_df.copy()
    display_df["timestamp"] = display_df["timestamp"].astype(str).str[:16]
    display_df["pnl_r"] = display_df["pnl_r"].apply(
        lambda x: f"+{x:.2f}R" if x > 0 else f"{x:.2f}R"
    )

    def color_outcome(val):
        if val == "win":
            return "background-color: #1a3a1a; color: #3fb950"
        elif val == "loss":
            return "background-color: #3a1a1a; color: #f85149"
        return ""

    styled = display_df.style.applymap(color_outcome, subset=["outcome"])
    st.dataframe(styled, use_container_width=True, height=400)

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv = trades_df.to_csv(index=False).encode()
        st.download_button("📥 Download Trade Log (CSV)", csv, "smc_trade_log.csv", "text/csv")


# ──────────────────────────────────────────────
# SMC Explanation Panel
# ──────────────────────────────────────────────

with st.expander("ℹ️ How This Robot Works — SMC Strategy Logic"):
    st.markdown("""
**Smart Money Concepts (SMC) Robot — Entry Logic**

1. **Liquidity Sweep Detection**
   - Scans for bars where the low wicks below a recent swing low then closes back above *(bullish sweep / stop hunt)*
   - Or the high wicks above a recent swing high then closes back below *(bearish sweep)*

2. **Order Block (OB) Confirmation**
   - After a bullish sweep → looks back for the last bearish candle before the structure break → marks it as a **Bullish Order Block**
   - After a bearish sweep → last bullish candle before the structure break → **Bearish Order Block**

3. **Fair Value Gap (FVG) Confirmation**
   - Detects 3-candle imbalances: `candle[i-2].high < candle[i].low` = bullish FVG
   - Entry triggers when price retraces into the OB or FVG zone within 5 bars

4. **Entry / SL / TP**
   - Entry at the midpoint of the OB or FVG zone
   - Stop Loss below the swept low (+ buffer) or above swept high
   - Take Profit = Entry ± Risk × R:R ratio

5. **Trade Management**
   - Force-close after `max_bars_open` if neither TP nor SL is hit
    """)
