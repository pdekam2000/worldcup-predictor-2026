"""
SMC Engine — Smart Money Concepts Detection
============================================
Implements the following SMC building blocks on a price DataFrame:

1. Swing Highs / Swing Lows  (pivot detection)
2. Break of Structure (BOS) and Change of Character (CHoCH)
3. Order Blocks (OB) — last opposite-colour candle before BOS
4. Fair Value Gaps (FVG) — 3-candle imbalance
5. Liquidity Sweeps — price wicks through a swing level then closes back

All functions accept a DataFrame with columns [open, high, low, close]
and return that same DataFrame with new annotation columns appended.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────
# 1. SWING HIGHS / LOWS
# ──────────────────────────────────────────────

def find_swings(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Detect swing highs and swing lows using a rolling pivot approach.

    Adds columns:
      swing_high : True where a confirmed swing high exists
      swing_low  : True where a confirmed swing low exists
    """
    df = df.copy()
    n = len(df)
    swing_high = np.zeros(n, dtype=bool)
    swing_low  = np.zeros(n, dtype=bool)

    for i in range(window, n - window):
        high_window = df["high"].iloc[i - window : i + window + 1]
        low_window  = df["low"].iloc[i - window : i + window + 1]

        if df["high"].iloc[i] == high_window.max():
            swing_high[i] = True
        if df["low"].iloc[i] == low_window.min():
            swing_low[i] = True

    df["swing_high"] = swing_high
    df["swing_low"]  = swing_low
    return df


# ──────────────────────────────────────────────
# 2. MARKET STRUCTURE — BOS / CHoCH
# ──────────────────────────────────────────────

def detect_structure(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify Break of Structure (BOS) and Change of Character (CHoCH).

    Adds columns:
      bos_bull, bos_bear, choch_bull, choch_bear, trend
    """
    df = df.copy()
    n = len(df)

    bos_bull   = np.zeros(n, dtype=bool)
    bos_bear   = np.zeros(n, dtype=bool)
    choch_bull = np.zeros(n, dtype=bool)
    choch_bear = np.zeros(n, dtype=bool)
    trend      = ["neutral"] * n

    last_sh_price = None
    last_sl_price = None
    current_trend = "neutral"

    for i in range(1, n):
        if df["swing_high"].iloc[i]:
            last_sh_price = df["high"].iloc[i]
        if df["swing_low"].iloc[i]:
            last_sl_price = df["low"].iloc[i]

        close = df["close"].iloc[i]

        if last_sh_price is not None and close > last_sh_price:
            if current_trend == "bull":
                bos_bull[i] = True
            else:
                choch_bull[i] = True
            current_trend = "bull"
            last_sh_price = None

        if last_sl_price is not None and close < last_sl_price:
            if current_trend == "bear":
                bos_bear[i] = True
            else:
                choch_bear[i] = True
            current_trend = "bear"
            last_sl_price = None

        trend[i] = current_trend

    df["bos_bull"]   = bos_bull
    df["bos_bear"]   = bos_bear
    df["choch_bull"] = choch_bull
    df["choch_bear"] = choch_bear
    df["trend"]      = trend
    return df


# ──────────────────────────────────────────────
# 3. ORDER BLOCKS — Active Zone Registry
# ──────────────────────────────────────────────

def build_order_block_registry(
    df: pd.DataFrame,
    lookback: int = 8,
    min_body_pct: float = 0.0003,  # body must be ≥ 0.03% of price (filters dojis)
) -> tuple[list[dict], list[dict]]:
    """
    Build two lists of all Order Block zones found in `df`.

    Filters out insignificant (doji) candles: the OB candle body must be
    at least `min_body_pct` × close price to qualify.

    Each entry: { 'bar': int, 'top': float, 'bot': float, 'mitigated': bool }
    """
    bull_obs: list[dict] = []
    bear_obs: list[dict] = []
    n = len(df)

    for i in range(lookback, n):
        price_ref = float(df["close"].iloc[i])
        min_body  = price_ref * min_body_pct

        # Bullish structure → find last meaningful bearish candle
        if df["bos_bull"].iloc[i] or df["choch_bull"].iloc[i]:
            for j in range(i - 1, max(i - lookback - 1, -1), -1):
                o = float(df["open"].iloc[j])
                c = float(df["close"].iloc[j])
                body = o - c  # positive for bearish
                if c < o and body >= min_body:
                    bull_obs.append({
                        "bar":       i,
                        "top":       o,
                        "bot":       float(df["low"].iloc[j]),
                        "mitigated": False,
                    })
                    break

        # Bearish structure → find last meaningful bullish candle
        if df["bos_bear"].iloc[i] or df["choch_bear"].iloc[i]:
            for j in range(i - 1, max(i - lookback - 1, -1), -1):
                o = float(df["open"].iloc[j])
                c = float(df["close"].iloc[j])
                body = c - o  # positive for bullish
                if c > o and body >= min_body:
                    bear_obs.append({
                        "bar":       i,
                        "top":       float(df["high"].iloc[j]),
                        "bot":       o,
                        "mitigated": False,
                    })
                    break

    return bull_obs, bear_obs


# ──────────────────────────────────────────────
# 4. FAIR VALUE GAPS — Active Zone Registry
# ──────────────────────────────────────────────

def build_fvg_registry(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """
    Build two lists of all FVG zones found in `df`:
      bull_fvgs : bullish FVGs (gap up)
      bear_fvgs : bearish FVGs (gap down)

    Each entry: { 'bar': int, 'top': float, 'bot': float, 'mitigated': bool }
    """
    bull_fvgs: list[dict] = []
    bear_fvgs: list[dict] = []
    n = len(df)

    for i in range(2, n):
        prev2_high = float(df["high"].iloc[i - 2])
        prev2_low  = float(df["low"].iloc[i - 2])
        curr_high  = float(df["high"].iloc[i])
        curr_low   = float(df["low"].iloc[i])
        gap_size   = curr_low - prev2_high if curr_low > prev2_high else prev2_low - curr_high

        # Minimum gap filter: 0.5 pips equivalent (relative to price)
        price_ref = float(df["close"].iloc[i])
        min_gap = price_ref * 0.00005  # 0.5 bps

        if curr_low > prev2_high and gap_size > min_gap:
            bull_fvgs.append({
                "bar": i,
                "top": curr_low,
                "bot": prev2_high,
                "mitigated": False,
            })

        if prev2_low > curr_high and gap_size > min_gap:
            bear_fvgs.append({
                "bar": i,
                "top": prev2_low,
                "bot": curr_high,
                "mitigated": False,
            })

    return bull_fvgs, bear_fvgs


# ──────────────────────────────────────────────
# 5. LIQUIDITY SWEEPS
# ──────────────────────────────────────────────

def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swing_window: int = 5,
    sweep_buffer_pct: float = 0.0002,  # 0.02% of price
) -> pd.DataFrame:
    """
    Detect liquidity sweeps (stop hunts).

    Adds columns:
      liq_sweep_bull  : True where a bullish sweep occurred
      liq_sweep_bear  : True where a bearish sweep occurred
      swept_low       : price level swept (bullish)
      swept_high      : price level swept (bearish)
    """
    df = df.copy()
    n = len(df)

    liq_sweep_bull = np.zeros(n, dtype=bool)
    liq_sweep_bear = np.zeros(n, dtype=bool)
    swept_low      = np.full(n, np.nan)
    swept_high     = np.full(n, np.nan)

    for i in range(swing_window * 2, n):
        bar_low    = float(df["low"].iloc[i])
        bar_high   = float(df["high"].iloc[i])
        bar_close  = float(df["close"].iloc[i])
        price_ref  = bar_close
        buf        = price_ref * sweep_buffer_pct

        window_start = max(0, i - 30)
        segment = df.iloc[window_start:i]
        recent_sl = segment.loc[segment["swing_low"],  "low"]
        recent_sh = segment.loc[segment["swing_high"], "high"]

        # Bullish sweep: wick below swing low, close back above
        for sl_price in recent_sl.values:
            if bar_low < sl_price - buf and bar_close > sl_price:
                liq_sweep_bull[i] = True
                swept_low[i] = float(sl_price)
                break

        # Bearish sweep: wick above swing high, close back below
        for sh_price in recent_sh.values:
            if bar_high > sh_price + buf and bar_close < sh_price:
                liq_sweep_bear[i] = True
                swept_high[i] = float(sh_price)
                break

    df["liq_sweep_bull"] = liq_sweep_bull
    df["liq_sweep_bear"] = liq_sweep_bear
    df["swept_low"]      = swept_low
    df["swept_high"]     = swept_high
    return df


# ──────────────────────────────────────────────
# FULL PIPELINE
# ──────────────────────────────────────────────

def run_smc_pipeline(
    df: pd.DataFrame,
    swing_window: int = 5,
    ob_lookback: int = 8,
    sweep_buffer_pct: float = 0.0002,
) -> tuple[pd.DataFrame, list[dict], list[dict], list[dict], list[dict]]:
    """
    Run all SMC detection steps.

    Returns
    -------
    (enriched_df, bull_obs, bear_obs, bull_fvgs, bear_fvgs)
    """
    df = find_swings(df, window=swing_window)
    df = detect_structure(df)
    df = detect_liquidity_sweeps(df, swing_window=swing_window, sweep_buffer_pct=sweep_buffer_pct)

    bull_obs,  bear_obs  = build_order_block_registry(df, lookback=ob_lookback)
    bull_fvgs, bear_fvgs = build_fvg_registry(df)

    return df, bull_obs, bear_obs, bull_fvgs, bear_fvgs
