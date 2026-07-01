"""
PedramScalper Pro — Python Backtest Engine
© Pedram Kamangar

Simulates the exact EA logic on real OHLCV data (yfinance, 1-minute bars)
Date range: 6 months ago → today
Pairs: EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, XAUUSD
"""

import warnings
warnings.filterwarnings("ignore")

import sys
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from tabulate import tabulate

# ─────────────────────────────────────────────────────────────────
# CONFIG — mirrors EA inputs
# ─────────────────────────────────────────────────────────────────
CFG = dict(
    # Trend
    ema_fast          = 50,
    ema_slow          = 200,
    adx_period        = 14,
    adx_min           = 20.0,
    trend_resample    = "1h",     # H1 equivalent

    # Scalp
    rsi_period        = 7,
    rsi_ob            = 70,
    rsi_os            = 30,
    stoch_k           = 5,
    stoch_d           = 3,
    stoch_slow        = 3,
    scalp_interval    = "30min",  # best proxy for 30s on daily data; use 5min for M1 proxy

    # SL / TP
    atr_period        = 14,
    atr_sl_mult       = 1.5,
    tp1_rr            = 1.0,
    tp2_rr            = 2.0,
    tp3_rr            = 3.0,

    # Martingale
    base_lot          = 0.01,
    mult_2x           = 2.0,
    mult_4x           = 4.0,
    max_consec_loss   = 4,

    # Risk
    max_dd_pct        = 10.0,
    starting_balance  = 10_000.0,
    pip_value_per_lot = 10.0,     # USD per pip per standard lot (majors)
    spread_pips       = 0.5,      # spread cost per trade
)

# ─────────────────────────────────────────────────────────────────
# SYMBOLS  (yfinance tickers)
# ─────────────────────────────────────────────────────────────────
SYMBOLS = {
    "EURUSD": {"ticker": "EURUSD=X", "pip": 0.0001, "desc": "Euro / US Dollar"},
    "USDJPY": {"ticker": "USDJPY=X", "pip": 0.01,   "desc": "US Dollar / Japanese Yen"},
    "GBPUSD": {"ticker": "GBPUSD=X", "pip": 0.0001, "desc": "British Pound / US Dollar"},
    "AUDUSD": {"ticker": "AUDUSD=X", "pip": 0.0001, "desc": "Australian Dollar / USD"},
    "USDCAD": {"ticker": "USDCAD=X", "pip": 0.0001, "desc": "US Dollar / Canadian Dollar"},
    "XAUUSD": {"ticker": "GC=F",     "pip": 0.01,   "desc": "Gold / US Dollar"},
}

# ─────────────────────────────────────────────────────────────────
# INDICATOR HELPERS
# ─────────────────────────────────────────────────────────────────
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=period - 1, adjust=False).mean()
    avg_l = loss.ewm(com=period - 1, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k: int, d: int, slow: int) -> tuple:
    lo  = low.rolling(k).min()
    hi  = high.rolling(k).max()
    raw = 100 * (close - lo) / (hi - lo + 1e-12)
    k_s = raw.rolling(slow).mean()
    d_s = k_s.rolling(d).mean()
    return k_s, d_s

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    idx        = high.index
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = close.shift(1)

    tr_raw = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    up   = (high - prev_high).fillna(0)
    down = (prev_low - low).fillna(0)

    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=idx)
    ndm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=idx)

    atr_s = tr_raw.ewm(com=period - 1, adjust=False).mean()
    pdi   = 100 * pdm.ewm(com=period - 1, adjust=False).mean() / atr_s
    ndi   = 100 * ndm.ewm(com=period - 1, adjust=False).mean() / atr_s
    dx    = 100 * (pdi - ndi).abs() / (pdi + ndi + 1e-12)
    return dx.ewm(com=period - 1, adjust=False).mean()

# ─────────────────────────────────────────────────────────────────
# DATA LOADER
# ─────────────────────────────────────────────────────────────────
def load_data(ticker: str, days: int = 183) -> pd.DataFrame:
    end   = datetime.now()
    start = end - timedelta(days=days)
    # Use 1h interval for trend + 5min for scalp signals (30s not available via yfinance)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"),
                     interval="1h", progress=False, auto_adjust=True)
    if df.empty:
        return df
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    df = df[["open","high","low","close","volume"]].dropna()
    return df

# ─────────────────────────────────────────────────────────────────
# SIGNAL BUILDER
# ─────────────────────────────────────────────────────────────────
def build_signals(df: pd.DataFrame, pip: float) -> pd.DataFrame:
    c = CFG
    d = df.copy()

    # ── Trend (same-TF EMAs + ADX, since we have H1 data)
    d["ema_fast"] = ema(d["close"], c["ema_fast"])
    d["ema_slow"] = ema(d["close"], c["ema_slow"])
    d["adx_val"]  = adx(d["high"], d["low"], d["close"], c["adx_period"])

    # ── Scalp indicators (RSI + Stoch on same bar — proxy for 30s cycle)
    d["rsi_val"]  = rsi(d["close"], c["rsi_period"])
    d["stoch_k"], d["stoch_d"] = stochastic(
        d["high"], d["low"], d["close"],
        c["stoch_k"], c["stoch_d"], c["stoch_slow"])

    d["atr_val"]  = atr(d["high"], d["low"], d["close"], c["atr_period"])

    # ── Trend direction
    d["trend"] = 0
    up   = (d["ema_fast"] > d["ema_slow"]) & (d["close"] > d["ema_fast"]) & (d["adx_val"] > c["adx_min"])
    down = (d["ema_fast"] < d["ema_slow"]) & (d["close"] < d["ema_fast"]) & (d["adx_val"] > c["adx_min"])
    d.loc[up,   "trend"] =  1
    d.loc[down, "trend"] = -1

    # ── Scalp signal
    rsi_cross_up = (d["rsi_val"].shift(1) < c["rsi_os"])  & (d["rsi_val"] >= c["rsi_os"])
    rsi_cross_dn = (d["rsi_val"].shift(1) > c["rsi_ob"])  & (d["rsi_val"] <= c["rsi_ob"])
    st_cross_up  = (d["stoch_k"].shift(1) < d["stoch_d"].shift(1)) & \
                   (d["stoch_k"] >= d["stoch_d"]) & (d["stoch_k"] < 50)
    st_cross_dn  = (d["stoch_k"].shift(1) > d["stoch_d"].shift(1)) & \
                   (d["stoch_k"] <= d["stoch_d"]) & (d["stoch_k"] > 50)

    d["signal"] = 0
    d.loc[(d["trend"] ==  1) & (rsi_cross_up | st_cross_up), "signal"] =  1
    d.loc[(d["trend"] == -1) & (rsi_cross_dn | st_cross_dn), "signal"] = -1

    return d.dropna()

# ─────────────────────────────────────────────────────────────────
# BACKTEST ENGINE
# ─────────────────────────────────────────────────────────────────
def run_backtest(symbol: str, df: pd.DataFrame, pip: float) -> dict:
    c       = CFG
    balance = c["starting_balance"]
    equity  = balance
    max_bal = balance
    max_dd  = 0.0
    halted  = False

    consec_loss = 0
    consec_win  = 0
    total = wins = losses = 0
    total_pnl = 0.0

    trades_log = []

    in_trade    = False
    entry_price = 0.0
    entry_dir   = 0
    entry_lot   = c["base_lot"]
    entry_sl    = 0.0
    entry_tp3   = 0.0
    sl_dist     = 0.0
    be_set      = False
    tp1_sl_set  = False
    cur_sl      = 0.0

    for i in range(1, len(df)):
        row      = df.iloc[i]
        prev_row = df.iloc[i - 1]

        if halted:
            break

        # ── Manage open trade
        if in_trade:
            hi   = row["high"]
            lo   = row["low"]
            bid  = row["close"]

            # ── Check SL hit
            sl_hit = (entry_dir == 1 and lo <= cur_sl) or \
                     (entry_dir == -1 and hi >= cur_sl)

            # ── Check TP3 hit
            tp_hit = (entry_dir == 1 and hi >= entry_tp3) or \
                     (entry_dir == -1 and lo <= entry_tp3)

            # ── Promote SL levels (TP1 → BE, TP2 → TP1 level)
            pnl_pts = (bid - entry_price) if entry_dir == 1 else (entry_price - bid)

            if not be_set and pnl_pts >= sl_dist * c["tp1_rr"]:
                cur_sl = entry_price + 2 * pip if entry_dir == 1 else entry_price - 2 * pip
                be_set = True

            if be_set and not tp1_sl_set and pnl_pts >= sl_dist * c["tp2_rr"]:
                tp1_level = (entry_price + sl_dist * c["tp1_rr"]) if entry_dir == 1 \
                            else (entry_price - sl_dist * c["tp1_rr"])
                cur_sl    = tp1_level
                tp1_sl_set = True

            # ── Trailing stop
            trail_dist = 15 * pip
            trail_start = 20 * pip
            if pnl_pts >= trail_start:
                if entry_dir == 1:
                    new_sl = bid - trail_dist
                    if new_sl > cur_sl:
                        cur_sl = new_sl
                else:
                    new_sl = bid + trail_dist
                    if new_sl < cur_sl:
                        cur_sl = new_sl

            # ── Close trade
            exit_price = None
            if sl_hit:
                exit_price = cur_sl
            elif tp_hit:
                exit_price = entry_tp3

            if exit_price is not None:
                raw_pnl = (exit_price - entry_price) if entry_dir == 1 \
                          else (entry_price - exit_price)
                # Convert to USD pnl
                pnl_pips = raw_pnl / pip
                pnl_usd  = (pnl_pips - c["spread_pips"]) * c["pip_value_per_lot"] * (entry_lot / 0.1)

                balance   += pnl_usd
                total_pnl += pnl_usd
                total     += 1

                if pnl_usd > 0:
                    wins       += 1
                    consec_loss = 0
                    consec_win += 1
                else:
                    losses     += 1
                    consec_win  = 0
                    consec_loss += 1

                if balance > max_bal:
                    max_bal = balance
                dd_now = (max_bal - balance) / max_bal * 100 if max_bal > 0 else 0
                if dd_now > max_dd:
                    max_dd = dd_now

                trades_log.append({
                    "time":      row.name,
                    "dir":       "BUY" if entry_dir == 1 else "SELL",
                    "lot":       entry_lot,
                    "entry":     entry_price,
                    "exit":      exit_price,
                    "pnl_usd":   round(pnl_usd, 2),
                    "balance":   round(balance, 2),
                    "result":    "WIN" if pnl_usd > 0 else "LOSS",
                })

                in_trade = False

                if consec_loss >= c["max_consec_loss"] or dd_now >= c["max_dd_pct"]:
                    halted = True
                    break

        # ── Look for new trade
        if not in_trade:
            sig = int(prev_row["signal"])  # use previous bar's confirmed signal
            if sig == 0:
                continue

            # Martingale lot
            if not c["base_lot"]:
                continue
            if consec_loss == 0:
                lot = c["base_lot"]
            elif consec_loss == 1:
                lot = c["base_lot"] * c["mult_2x"]
            else:
                lot = c["base_lot"] * c["mult_4x"]

            atr_v  = prev_row["atr_val"]
            sl_d   = atr_v * c["atr_sl_mult"]

            if sig == 1:   # BUY
                ep   = row["open"]
                e_sl = ep - sl_d
                e_tp = ep + sl_d * c["tp3_rr"]
            else:           # SELL
                ep   = row["open"]
                e_sl = ep + sl_d
                e_tp = ep - sl_d * c["tp3_rr"]

            in_trade    = True
            entry_price = ep
            entry_dir   = sig
            entry_lot   = lot
            entry_sl    = e_sl
            entry_tp3   = e_tp
            cur_sl      = e_sl
            sl_dist     = sl_d
            be_set      = False
            tp1_sl_set  = False

    wr = wins / total * 100 if total > 0 else 0
    pf_denom = abs(sum(t["pnl_usd"] for t in trades_log if t["pnl_usd"] < 0))
    pf_num   = sum(t["pnl_usd"] for t in trades_log if t["pnl_usd"] > 0)
    pf       = pf_num / pf_denom if pf_denom > 0 else float("inf")
    final_bal = balance
    ret_pct   = (final_bal - c["starting_balance"]) / c["starting_balance"] * 100

    return {
        "symbol":       symbol,
        "total_trades": total,
        "wins":         wins,
        "losses":       losses,
        "win_rate":     round(wr, 1),
        "net_pnl":      round(total_pnl, 2),
        "return_pct":   round(ret_pct, 2),
        "profit_factor":round(pf, 2),
        "max_dd_pct":   round(max_dd, 2),
        "final_balance":round(final_bal, 2),
        "halted":       halted,
        "trades_log":   trades_log,
    }

# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    print("\n" + "═" * 70)
    print("  PEDRAM SCALPER PRO — PYTHON BACKTEST ENGINE")
    print("  © Pedram Kamangar")
    date_from = (datetime.now() - timedelta(days=183)).strftime("%Y-%m-%d")
    date_to   = datetime.now().strftime("%Y-%m-%d")
    print(f"  Period : {date_from}  →  {date_to}  (6 months)")
    print(f"  Balance: ${CFG['starting_balance']:,.0f}  |  Spread: {CFG['spread_pips']} pips")
    print(f"  Martingale: 1×  →  2×  →  4×  |  Max Loss Streak: {CFG['max_consec_loss']}")
    print(f"  ATR SL ×{CFG['atr_sl_mult']}  |  TP: {CFG['tp1_rr']}:{CFG['tp2_rr']}:{CFG['tp3_rr']} R/R")
    print("═" * 70)

    results = []
    all_trades = {}

    for sym, meta in SYMBOLS.items():
        sys.stdout.write(f"  Downloading {sym:8s} ({meta['desc']}) ... ")
        sys.stdout.flush()
        df = load_data(meta["ticker"])
        if df.empty or len(df) < CFG["ema_slow"] + 50:
            print("⚠ Not enough data — skipped")
            continue

        df = build_signals(df, meta["pip"])
        res = run_backtest(sym, df, meta["pip"])
        results.append(res)
        all_trades[sym] = res["trades_log"]

        star = "⭐" if res["win_rate"] >= 55 and res["profit_factor"] >= 1.3 else ""
        halt = " 🛑HALTED" if res["halted"] else ""
        print(f"✔  {res['total_trades']} trades | WR={res['win_rate']}% | "
              f"PF={res['profit_factor']} | DD={res['max_dd_pct']}% | "
              f"PnL=${res['net_pnl']:+,.2f} {star}{halt}")

    if not results:
        print("\n  No results to display.")
        return

    # ── Summary table
    print("\n" + "═" * 70)
    print("  SUMMARY TABLE")
    print("═" * 70)
    table_rows = []
    for r in sorted(results, key=lambda x: x["profit_factor"], reverse=True):
        rank = "⭐ BEST" if r["profit_factor"] >= 1.3 and r["win_rate"] >= 55 else \
               "✔ GOOD" if r["profit_factor"] >= 1.1 else "✗ WEAK"
        table_rows.append([
            r["symbol"],
            r["total_trades"],
            f"{r['win_rate']}%",
            r["profit_factor"],
            f"{r['max_dd_pct']}%",
            f"${r['net_pnl']:+,.2f}",
            f"{r['return_pct']:+.1f}%",
            f"${r['final_balance']:,.2f}",
            rank,
        ])

    print(tabulate(
        table_rows,
        headers=["Symbol","Trades","Win%","Profit Factor","Max DD%",
                 "Net PnL","Return%","Balance","Verdict"],
        tablefmt="rounded_outline",
        stralign="right",
    ))

    # ── Best pair detail
    best = max(results, key=lambda x: x["profit_factor"])
    print(f"\n  BEST PAIR: {best['symbol']} (Profit Factor = {best['profit_factor']})")
    print(f"  Trades: {best['total_trades']}  |  Wins: {best['wins']}  |  "
          f"Losses: {best['losses']}  |  Win Rate: {best['win_rate']}%")
    print(f"  Net P/L: ${best['net_pnl']:+,.2f}  |  Max DD: {best['max_dd_pct']}%  |  "
          f"Final Balance: ${best['final_balance']:,.2f}")

    # ── Monthly breakdown for best pair
    tlog = all_trades.get(best["symbol"], [])
    if tlog:
        print(f"\n  MONTHLY BREAKDOWN — {best['symbol']}")
        print("  " + "─" * 60)
        mdf = pd.DataFrame(tlog)
        mdf["month"] = pd.to_datetime(mdf["time"]).dt.to_period("M")
        monthly = mdf.groupby("month").agg(
            Trades=("pnl_usd","count"),
            Wins=("result", lambda x: (x=="WIN").sum()),
            PnL=("pnl_usd","sum"),
        ).reset_index()
        monthly["WR%"] = (monthly["Wins"] / monthly["Trades"] * 100).round(1)
        monthly["PnL"]= monthly["PnL"].round(2)
        print(tabulate(
            monthly[["month","Trades","Wins","WR%","PnL"]].values.tolist(),
            headers=["Month","Trades","Wins","Win%","Net PnL ($)"],
            tablefmt="simple",
        ))

    # ── Recommendations
    print("\n" + "═" * 70)
    print("  RECOMMENDATIONS")
    print("═" * 70)
    for r in sorted(results, key=lambda x: x["profit_factor"], reverse=True)[:3]:
        verdict = ""
        if r["profit_factor"] >= 1.3 and r["win_rate"] >= 55:
            verdict = "✅ Recommended — strong edge"
        elif r["profit_factor"] >= 1.1:
            verdict = "🟡 Marginal — optimize parameters"
        else:
            verdict = "❌ Not recommended — negative edge"
        print(f"  {r['symbol']:8s}  PF={r['profit_factor']}  WR={r['win_rate']}%  "
              f"DD={r['max_dd_pct']}%  →  {verdict}")

    print("\n  NOTE: This backtest uses 1-hour bars as proxy for 30-second intervals.")
    print("        For highest fidelity, run in MT5 Strategy Tester with 'Every Tick' model.")
    print("        Real 30-second data is only available inside MT5.")
    print("═" * 70 + "\n")

if __name__ == "__main__":
    main()
