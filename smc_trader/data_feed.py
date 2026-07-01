"""
SMC Trader - Data Feed
Fetches OHLCV data for forex pairs using yfinance.
Covers the last 3 months on H1 and H4 timeframes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import yfinance as yf


# Popular forex pairs as Yahoo Finance tickers
POPULAR_PAIRS: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "GBPJPY": "GBPJPY=X",
    "XAUUSD": "GC=F",       # Gold (XAU/USD) via futures
}

TIMEFRAME_MAP: dict[str, str] = {
    "H1":  "1h",
    "H4":  "1h",   # will resample from H1
    "D1":  "1d",
    "M15": "15m",
    "M5":  "5m",
}


def fetch_ohlcv(
    pair: str,
    timeframe: str = "H1",
    months: int = 3,
) -> pd.DataFrame:
    """
    Download OHLCV data for a forex pair.

    Parameters
    ----------
    pair      : e.g. 'EURUSD'
    timeframe : 'M15', 'H1', 'H4', 'D1'
    months    : how many months of history to pull

    Returns
    -------
    DataFrame with columns: open, high, low, close, volume
    indexed by UTC datetime.
    """
    ticker = POPULAR_PAIRS.get(pair.upper())
    if ticker is None:
        raise ValueError(
            f"Unknown pair '{pair}'. Available: {list(POPULAR_PAIRS.keys())}"
        )

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=months * 31)

    # yfinance intraday limit: max 60 days for 1h, 7 days for 15m
    yf_interval = "1h"
    if timeframe in ("M15", "M5"):
        yf_interval = "15m"
        if months > 1:
            months = 1  # cap to avoid yfinance limit
            start = end - timedelta(days=60)
    elif timeframe == "D1":
        yf_interval = "1d"

    raw = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=yf_interval,
        progress=False,
        auto_adjust=True,
    )

    if raw.empty:
        raise RuntimeError(f"No data returned for {pair} ({ticker})")

    # Flatten MultiIndex columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index = pd.to_datetime(df.index, utc=True)
    df.sort_index(inplace=True)
    df.dropna(inplace=True)

    if timeframe == "H4":
        df = _resample_h4(df)

    return df


def _resample_h4(df: pd.DataFrame) -> pd.DataFrame:
    """Resample H1 data into H4 bars."""
    df_h4 = df.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return df_h4.dropna()


def fetch_all_pairs(
    timeframe: str = "H1",
    months: int = 3,
    pairs: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """
    Download data for multiple pairs.
    Returns a dict: {pair_name: DataFrame}
    """
    target = pairs or list(POPULAR_PAIRS.keys())
    result: dict[str, pd.DataFrame] = {}

    for pair in target:
        try:
            df = fetch_ohlcv(pair, timeframe=timeframe, months=months)
            result[pair] = df
            print(f"  [{pair}] {len(df)} bars loaded ({timeframe})")
        except Exception as exc:
            print(f"  [{pair}] SKIP — {exc}")

    return result


if __name__ == "__main__":
    print("Fetching EURUSD H1 (3 months)...")
    df = fetch_ohlcv("EURUSD", timeframe="H1", months=3)
    print(df.tail())
    print(f"Total bars: {len(df)}")
