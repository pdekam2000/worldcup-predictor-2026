# SMC Forex Robot Trader

A fully automatic **Smart Money Concepts (SMC)** algorithmic trading robot with
a backtesting engine and interactive Streamlit dashboard.

## What It Does

The robot identifies high-probability trade setups by combining three core SMC tools:

| Tool | Description |
|------|-------------|
| **Liquidity Sweep** | Detects price wicking through a swing high/low then closing back |
| **Order Block (OB)** | Last meaningful opposite-colour candle before a Break of Structure |
| **Fair Value Gap (FVG)** | 3-candle imbalance zone where institutional orders are expected |

### Entry Logic (Long)
1. Price sweeps below a recent swing low (stop hunt — liquidity taken)
2. Within the next `confirmation_bars`, price retraces into a bullish OB or FVG
3. Entry at zone midpoint, stop below swept low, target = entry + risk × RR

### Entry Logic (Short)
Symmetric: price sweeps above swing high → retraces into bearish OB/FVG → short entry.

---

## 3-Month Backtest Results (H1, 7 Pairs)

| Metric | Value |
|--------|-------|
| Total Trades | 30 |
| Win Rate | 40.0% |
| Net R Gained | **+2.52R** |
| Profit Factor | **1.15** |
| Avg Win | 1.65R |
| Avg Loss | 0.96R |
| Max Drawdown | -5.0R |

**Pairs traded:** EUR/USD · GBP/USD · USD/JPY · AUD/USD · USD/CAD · GBP/JPY · XAU/USD

> Note: A 40% win rate is profitable at 2:1 R:R (breakeven = 33.3%).

---

## Installation

```bash
pip install -r smc_trader/requirements.txt
```

---

## Usage

### Run Backtest (Terminal)

```bash
python3 smc_trader/run_backtest.py \
  --pairs EURUSD GBPUSD USDJPY AUDUSD USDCAD GBPJPY XAUUSD \
  --tf H1 \
  --months 3 \
  --rr 2.0 \
  --output smc_results
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--pairs` | All 7 | Space-separated list of pairs |
| `--tf` | `H1` | Timeframe: `M15`, `H1`, `H4`, `D1` |
| `--months` | `3` | History depth in months |
| `--rr` | `2.0` | Take-profit reward-to-risk ratio |
| `--output` | `smc_results/` | Output directory for reports |

### Launch Dashboard (Streamlit)

```bash
~/.local/bin/streamlit run smc_trader/dashboard.py
```

Opens an interactive browser dashboard with:
- Live backtest controls (pair selection, timeframe, R:R ratio, SMC parameters)
- Combined & per-pair equity curves (Plotly)
- Colour-coded trade log with CSV export
- SMC strategy explanation panel

---

## Supported Pairs

| Symbol | Yahoo Finance Ticker |
|--------|---------------------|
| EURUSD | `EURUSD=X` |
| GBPUSD | `GBPUSD=X` |
| USDJPY | `USDJPY=X` |
| AUDUSD | `AUDUSD=X` |
| USDCAD | `USDCAD=X` |
| GBPJPY | `GBPJPY=X` |
| XAUUSD (Gold) | `GC=F` |

---

## Output Files

After each run, the `--output` directory contains:

| File | Description |
|------|-------------|
| `smc_backtest_report.png` | Multi-panel equity curve chart |
| `trade_log.csv` | Full trade-by-trade record |
| `metrics.json` | Aggregated performance metrics |

---

## Module Structure

```
smc_trader/
├── data_feed.py      — OHLCV download via yfinance (H1, H4, D1)
├── smc_engine.py     — Swing detection, BOS/CHoCH, OBs, FVGs, sweeps
├── strategy.py       — Signal generation (sweep + zone confluence)
├── backtester.py     — Trade simulation, TP/SL walk-forward
├── report.py         — Terminal report + Matplotlib chart
├── run_backtest.py   — CLI runner
├── dashboard.py      — Streamlit interactive dashboard
└── requirements.txt
```

---

## SMC Concepts Implemented

- **Swing High / Swing Low** — Pivot detection with configurable window
- **Break of Structure (BOS)** — Continuation signal, trend confirmed
- **Change of Character (CHoCH)** — Reversal signal, trend may be shifting
- **Order Block** — Institutional footprint (last meaningful opposite candle before BOS)
- **Fair Value Gap** — Imbalance left by fast institutional moves
- **Liquidity Sweep** — Wick through swing level then close back (stop hunt)
- **Active Zone Registry** — Zones tracked as mitigated or active across the whole chart

---

## Risk Warning

> This is a research/educational tool. Backtesting results do not guarantee future
> performance. Always paper-trade first and apply proper risk management.
