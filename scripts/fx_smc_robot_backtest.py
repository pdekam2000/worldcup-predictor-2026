#!/usr/bin/env python3
"""FX SMC-style paper robot and three-month backtester.

This script is intentionally isolated from the football prediction runtime. It
does not place live orders. It builds bracket trade plans and evaluates them on
historical FX bars for research/paper-trading only.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


POPULAR_FX_PAIRS: dict[str, dict[str, str]] = {
    "EURUSD": {"yahoo": "EURUSD=X", "stooq": "eurusd"},
    "GBPUSD": {"yahoo": "GBPUSD=X", "stooq": "gbpusd"},
    "USDJPY": {"yahoo": "USDJPY=X", "stooq": "usdjpy"},
    "USDCHF": {"yahoo": "USDCHF=X", "stooq": "usdchf"},
    "USDCAD": {"yahoo": "USDCAD=X", "stooq": "usdcad"},
    "AUDUSD": {"yahoo": "AUDUSD=X", "stooq": "audusd"},
    "NZDUSD": {"yahoo": "NZDUSD=X", "stooq": "nzdusd"},
}

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; fx-smc-paper-backtester/1.0)"


@dataclass(frozen=True)
class PriceBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class StrategyParams:
    name: str
    lookback_bars: int = 24
    atr_period: int = 14
    rr: float = 1.5
    max_hold_bars: int = 24
    min_score: float = 0.64
    stop_atr_buffer: float = 0.12
    min_stop_atr: float = 0.20
    session_start_utc: int = 6
    session_end_utc: int = 17
    risk_per_trade: float = 0.01
    cost_r: float = 0.03

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradeSignal:
    pair: str
    side: str
    signal_time: datetime
    entry_time: datetime
    entry: float
    stop: float
    target: float
    score: float
    reasons: list[str]

    @property
    def risk_distance(self) -> float:
        return abs(self.entry - self.stop)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["signal_time"] = self.signal_time.isoformat()
        data["entry_time"] = self.entry_time.isoformat()
        return data


@dataclass(frozen=True)
class TradeResult:
    pair: str
    side: str
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry: float
    stop: float
    target: float
    exit_price: float
    exit_reason: str
    score: float
    r_multiple: float
    pnl: float
    balance_after: float
    reasons: list[str]

    @property
    def won(self) -> bool:
        return self.r_multiple > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["signal_time"] = self.signal_time.isoformat()
        data["entry_time"] = self.entry_time.isoformat()
        data["exit_time"] = self.exit_time.isoformat()
        return data


@dataclass(frozen=True)
class DataLoadResult:
    pair: str
    provider: str
    bars: list[PriceBar]
    errors: list[str]

    def to_quality_dict(self) -> dict[str, Any]:
        first = self.bars[0].timestamp.isoformat() if self.bars else None
        last = self.bars[-1].timestamp.isoformat() if self.bars else None
        return {
            "pair": self.pair,
            "provider": self.provider,
            "bars": len(self.bars),
            "first_bar": first,
            "last_bar": last,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class Metrics:
    trades: int
    wins: int
    losses: int
    win_rate: float | None
    net_r: float
    average_r: float
    profit_factor: float | None
    expectancy_r: float
    return_pct: float
    max_drawdown_pct: float
    best_r: float | None
    worst_r: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PairBacktest:
    pair: str
    metrics: Metrics
    trades: list[TradeResult]
    last_signal: dict[str, Any] | None
    data_quality: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "metrics": self.metrics.to_dict(),
            "last_signal": self.last_signal,
            "data_quality": self.data_quality,
            "trades": [trade.to_dict() for trade in self.trades],
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def fetch_url_text(url: str, *, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def fetch_yahoo_bars(pair: str, *, months: int, interval: str) -> DataLoadResult:
    symbol = POPULAR_FX_PAIRS[pair]["yahoo"]
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(symbol)}?range={months}mo&interval={quote(interval)}"
        "&includePrePost=false"
    )
    errors: list[str] = []
    try:
        payload = json.loads(fetch_url_text(url))
        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(str(chart["error"]))
        result = (chart.get("result") or [None])[0]
        if not result:
            raise RuntimeError("Yahoo returned no chart result")
        timestamps = result.get("timestamp") or []
        quote_block = ((result.get("indicators") or {}).get("quote") or [None])[0]
        if not quote_block:
            raise RuntimeError("Yahoo returned no OHLC quote block")
        bars = _bars_from_yahoo(pair, timestamps, quote_block)
        if not bars:
            raise RuntimeError("Yahoo returned no usable OHLC bars")
        return DataLoadResult(pair=pair, provider="yahoo_chart", bars=bars, errors=errors)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"yahoo_chart: {exc}")
        return DataLoadResult(pair=pair, provider="yahoo_chart", bars=[], errors=errors)


def _bars_from_yahoo(pair: str, timestamps: list[int], quote_block: dict[str, Any]) -> list[PriceBar]:
    opens = quote_block.get("open") or []
    highs = quote_block.get("high") or []
    lows = quote_block.get("low") or []
    closes = quote_block.get("close") or []
    bars: list[PriceBar] = []
    for ts, open_, high, low, close in zip(timestamps, opens, highs, lows, closes):
        if None in (open_, high, low, close):
            continue
        try:
            bar = PriceBar(
                timestamp=datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(microsecond=0),
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                source=f"yahoo:{pair}",
            )
        except (TypeError, ValueError, OSError):
            continue
        if bar.high < bar.low or min(bar.open, bar.close) <= 0:
            continue
        bars.append(bar)
    return _dedupe_and_sort_bars(bars)


def fetch_stooq_daily_bars(pair: str, *, months: int) -> DataLoadResult:
    symbol = POPULAR_FX_PAIRS[pair]["stooq"]
    end = utc_now().date()
    start = end - timedelta(days=max(30, months * 31 + 7))
    url = (
        "https://stooq.com/q/d/l/"
        f"?s={quote(symbol)}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
    )
    errors: list[str] = []
    try:
        text = fetch_url_text(url)
        reader = csv.DictReader(io.StringIO(text))
        bars: list[PriceBar] = []
        for row in reader:
            if not row or row.get("Date") in (None, "No data"):
                continue
            try:
                stamp = datetime.strptime(str(row["Date"]), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                bars.append(
                    PriceBar(
                        timestamp=stamp,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        source=f"stooq:{pair}",
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not bars:
            raise RuntimeError("Stooq returned no usable OHLC bars")
        return DataLoadResult(pair=pair, provider="stooq_daily", bars=_dedupe_and_sort_bars(bars), errors=errors)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"stooq_daily: {exc}")
        return DataLoadResult(pair=pair, provider="stooq_daily", bars=[], errors=errors)


def load_pair_data(pair: str, *, months: int, interval: str) -> DataLoadResult:
    primary = fetch_yahoo_bars(pair, months=months, interval=interval)
    if primary.bars:
        return primary
    fallback = fetch_stooq_daily_bars(pair, months=months)
    return DataLoadResult(
        pair=pair,
        provider=fallback.provider if fallback.bars else "unavailable",
        bars=fallback.bars,
        errors=[*primary.errors, *fallback.errors],
    )


def _dedupe_and_sort_bars(bars: list[PriceBar]) -> list[PriceBar]:
    by_time: dict[datetime, PriceBar] = {}
    for bar in bars:
        by_time[bar.timestamp] = bar
    return [by_time[key] for key in sorted(by_time)]


def true_ranges(bars: list[PriceBar]) -> list[float]:
    ranges: list[float] = []
    previous_close: float | None = None
    for bar in bars:
        if previous_close is None:
            ranges.append(bar.high - bar.low)
        else:
            ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        previous_close = bar.close
    return ranges


def rolling_average(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    window: list[float] = []
    for value in values:
        window.append(value)
        if len(window) > period:
            window.pop(0)
        output.append(mean(window) if len(window) == period else None)
    return output


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 1:
        return [float(v) for v in values]
    output: list[float | None] = []
    multiplier = 2.0 / (period + 1)
    current: float | None = None
    seed: list[float] = []
    for value in values:
        if current is None:
            seed.append(value)
            if len(seed) < period:
                output.append(None)
                continue
            current = mean(seed)
            output.append(current)
            continue
        current = (value - current) * multiplier + current
        output.append(current)
    return output


def build_signal(
    pair: str,
    bars: list[PriceBar],
    index: int,
    params: StrategyParams,
    atr_values: list[float | None],
    ema_fast: list[float | None],
    ema_slow: list[float | None],
) -> TradeSignal | None:
    if index < params.lookback_bars or index + 1 >= len(bars):
        return None

    signal_bar = bars[index]
    entry_bar = bars[index + 1]
    if not _inside_session(signal_bar, params):
        return None

    atr = atr_values[index]
    if atr is None or atr <= 0:
        return None

    previous = bars[index - params.lookback_bars : index]
    previous_high = max(bar.high for bar in previous)
    previous_low = min(bar.low for bar in previous)
    previous_range = max(previous_high - previous_low, atr)
    midpoint = previous_low + previous_range * 0.5

    body = abs(signal_bar.close - signal_bar.open)
    candle_range = max(signal_bar.high - signal_bar.low, 1e-12)
    lower_wick = min(signal_bar.open, signal_bar.close) - signal_bar.low
    upper_wick = signal_bar.high - max(signal_bar.open, signal_bar.close)
    liquidity_buffer = max(atr * 0.03, previous_range * 0.001)

    bullish_sweep = signal_bar.low < previous_low - liquidity_buffer and signal_bar.close > previous_low
    bearish_sweep = signal_bar.high > previous_high + liquidity_buffer and signal_bar.close < previous_high

    if bullish_sweep:
        score = 0.52
        reasons = ["sell-side liquidity swept and reclaimed"]
        if signal_bar.close > signal_bar.open:
            score += 0.08
            reasons.append("bullish rejection close")
        if lower_wick / candle_range >= 0.35 or lower_wick >= body:
            score += 0.10
            reasons.append("long lower wick rejection")
        if signal_bar.close <= midpoint:
            score += 0.06
            reasons.append("entry forms in discount half of recent range")
        if ema_fast[index] is not None and ema_slow[index] is not None and ema_fast[index] >= ema_slow[index]:
            score += 0.06
            reasons.append("structure filter aligned")
        if (previous_low - signal_bar.low) >= atr * 0.15:
            score += 0.05
            reasons.append("meaningful liquidity displacement")
        return _make_signal(
            pair=pair,
            side="long",
            bars=bars,
            signal_index=index,
            entry=entry_bar.open,
            extreme=signal_bar.low,
            atr=atr,
            score=score,
            reasons=reasons,
            params=params,
        )

    if bearish_sweep:
        score = 0.52
        reasons = ["buy-side liquidity swept and reclaimed"]
        if signal_bar.close < signal_bar.open:
            score += 0.08
            reasons.append("bearish rejection close")
        if upper_wick / candle_range >= 0.35 or upper_wick >= body:
            score += 0.10
            reasons.append("long upper wick rejection")
        if signal_bar.close >= midpoint:
            score += 0.06
            reasons.append("entry forms in premium half of recent range")
        if ema_fast[index] is not None and ema_slow[index] is not None and ema_fast[index] <= ema_slow[index]:
            score += 0.06
            reasons.append("structure filter aligned")
        if (signal_bar.high - previous_high) >= atr * 0.15:
            score += 0.05
            reasons.append("meaningful liquidity displacement")
        return _make_signal(
            pair=pair,
            side="short",
            bars=bars,
            signal_index=index,
            entry=entry_bar.open,
            extreme=signal_bar.high,
            atr=atr,
            score=score,
            reasons=reasons,
            params=params,
        )

    return None


def _inside_session(bar: PriceBar, params: StrategyParams) -> bool:
    hour = bar.timestamp.hour
    start = params.session_start_utc
    end = params.session_end_utc
    if start == end:
        return True
    if start < end:
        return start <= hour <= end
    return hour >= start or hour <= end


def _make_signal(
    *,
    pair: str,
    side: str,
    bars: list[PriceBar],
    signal_index: int,
    entry: float,
    extreme: float,
    atr: float,
    score: float,
    reasons: list[str],
    params: StrategyParams,
) -> TradeSignal | None:
    if score < params.min_score:
        return None
    if side == "long":
        stop = extreme - atr * params.stop_atr_buffer
        risk = entry - stop
        target = entry + risk * params.rr
    else:
        stop = extreme + atr * params.stop_atr_buffer
        risk = stop - entry
        target = entry - risk * params.rr
    if risk <= atr * params.min_stop_atr or risk <= 0:
        return None
    return TradeSignal(
        pair=pair,
        side=side,
        signal_time=bars[signal_index].timestamp,
        entry_time=bars[signal_index + 1].timestamp,
        entry=entry,
        stop=stop,
        target=target,
        score=round(min(score, 0.99), 4),
        reasons=reasons,
    )


def backtest_pair(
    pair: str,
    bars: list[PriceBar],
    params: StrategyParams,
    *,
    start_balance: float,
) -> PairBacktest:
    atr_values = rolling_average(true_ranges(bars), params.atr_period)
    closes = [bar.close for bar in bars]
    ema_fast = ema(closes, max(6, params.lookback_bars // 2))
    ema_slow = ema(closes, max(12, params.lookback_bars * 2))

    trades: list[TradeResult] = []
    balance = start_balance
    index = max(params.lookback_bars, params.atr_period)
    latest_candidate: TradeSignal | None = None

    while index + 1 < len(bars):
        signal = build_signal(pair, bars, index, params, atr_values, ema_fast, ema_slow)
        if signal is None:
            index += 1
            continue

        latest_candidate = signal
        trade, exit_index = _simulate_trade(signal, bars, index + 1, params, balance)
        balance = trade.balance_after
        trades.append(trade)
        index = max(exit_index + 1, index + 1)

    last_signal = latest_candidate.to_dict() if latest_candidate else None
    quality = {
        "pair": pair,
        "provider": bars[0].source.split(":", 1)[0] if bars else "unknown",
        "bars": len(bars),
        "first_bar": bars[0].timestamp.isoformat() if bars else None,
        "last_bar": bars[-1].timestamp.isoformat() if bars else None,
    }
    return PairBacktest(
        pair=pair,
        metrics=summarize_trades(trades, start_balance=start_balance, risk_per_trade=params.risk_per_trade),
        trades=trades,
        last_signal=last_signal,
        data_quality=quality,
    )


def _simulate_trade(
    signal: TradeSignal,
    bars: list[PriceBar],
    entry_index: int,
    params: StrategyParams,
    balance: float,
) -> tuple[TradeResult, int]:
    max_exit_index = min(len(bars) - 1, entry_index + params.max_hold_bars)
    exit_price = bars[max_exit_index].close
    exit_time = bars[max_exit_index].timestamp
    exit_reason = "time_exit"
    exit_index = max_exit_index

    for index in range(entry_index, max_exit_index + 1):
        bar = bars[index]
        if signal.side == "long":
            stop_hit = bar.low <= signal.stop
            target_hit = bar.high >= signal.target
            if stop_hit and target_hit:
                exit_price = signal.stop
                exit_reason = "stop_before_target_conservative"
            elif stop_hit:
                exit_price = signal.stop
                exit_reason = "stop"
            elif target_hit:
                exit_price = signal.target
                exit_reason = "target"
            else:
                continue
        else:
            stop_hit = bar.high >= signal.stop
            target_hit = bar.low <= signal.target
            if stop_hit and target_hit:
                exit_price = signal.stop
                exit_reason = "stop_before_target_conservative"
            elif stop_hit:
                exit_price = signal.stop
                exit_reason = "stop"
            elif target_hit:
                exit_price = signal.target
                exit_reason = "target"
            else:
                continue
        exit_time = bar.timestamp
        exit_index = index
        break

    raw_r = _r_multiple(signal.side, signal.entry, exit_price, signal.risk_distance)
    r_multiple = round(raw_r - params.cost_r, 4)
    risk_amount = balance * params.risk_per_trade
    pnl = risk_amount * r_multiple
    balance_after = balance + pnl
    return (
        TradeResult(
            pair=signal.pair,
            side=signal.side,
            signal_time=signal.signal_time,
            entry_time=signal.entry_time,
            exit_time=exit_time,
            entry=signal.entry,
            stop=signal.stop,
            target=signal.target,
            exit_price=exit_price,
            exit_reason=exit_reason,
            score=signal.score,
            r_multiple=r_multiple,
            pnl=round(pnl, 2),
            balance_after=round(balance_after, 2),
            reasons=signal.reasons,
        ),
        exit_index,
    )


def _r_multiple(side: str, entry: float, exit_price: float, risk_distance: float) -> float:
    if risk_distance <= 0:
        return 0.0
    if side == "long":
        return (exit_price - entry) / risk_distance
    return (entry - exit_price) / risk_distance


def summarize_trades(
    trades: list[TradeResult],
    *,
    start_balance: float,
    risk_per_trade: float,
) -> Metrics:
    if not trades:
        return Metrics(
            trades=0,
            wins=0,
            losses=0,
            win_rate=None,
            net_r=0.0,
            average_r=0.0,
            profit_factor=None,
            expectancy_r=0.0,
            return_pct=0.0,
            max_drawdown_pct=0.0,
            best_r=None,
            worst_r=None,
        )

    sorted_trades = sorted(trades, key=lambda trade: trade.exit_time)
    balance = start_balance
    peak = start_balance
    max_drawdown = 0.0
    r_values = [trade.r_multiple for trade in sorted_trades]
    wins = [value for value in r_values if value > 0]
    losses = [value for value in r_values if value <= 0]
    for trade in sorted_trades:
        balance += balance * risk_per_trade * trade.r_multiple
        peak = max(peak, balance)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - balance) / peak)

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return Metrics(
        trades=len(sorted_trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(len(wins) / len(sorted_trades), 4),
        net_r=round(sum(r_values), 4),
        average_r=round(mean(r_values), 4),
        profit_factor=round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
        expectancy_r=round(mean(r_values), 4),
        return_pct=round((balance - start_balance) / start_balance * 100, 4),
        max_drawdown_pct=round(max_drawdown * 100, 4),
        best_r=round(max(r_values), 4),
        worst_r=round(min(r_values), 4),
    )


def build_parameter_grid(base: StrategyParams) -> list[StrategyParams]:
    grid: list[StrategyParams] = []
    for lookback in (12, 18, 24, 36):
        for rr in (1.1, 1.35, 1.6, 2.0):
            for max_hold in (12, 24, 36):
                for min_score in (0.62, 0.68, 0.74):
                    grid.append(
                        replace(
                            base,
                            name=f"smc_lq_lb{lookback}_rr{rr:g}_h{max_hold}_s{min_score:g}",
                            lookback_bars=lookback,
                            rr=rr,
                            max_hold_bars=max_hold,
                            min_score=min_score,
                        )
                    )
    return grid


def optimize_params(
    bars_by_pair: dict[str, list[PriceBar]],
    base: StrategyParams,
    *,
    start_balance: float,
    min_trades: int,
) -> tuple[StrategyParams, list[dict[str, Any]]]:
    trials: list[dict[str, Any]] = []
    for params in build_parameter_grid(base):
        all_trades: list[TradeResult] = []
        active_pairs = 0
        for pair, bars in bars_by_pair.items():
            result = backtest_pair(pair, bars, params, start_balance=start_balance)
            if result.trades:
                active_pairs += 1
            all_trades.extend(result.trades)
        metrics = summarize_trades(all_trades, start_balance=start_balance, risk_per_trade=params.risk_per_trade)
        trade_penalty = 3.0 if metrics.trades < min_trades else 0.0
        pair_penalty = max(0, 4 - active_pairs) * 0.35
        score = metrics.net_r - metrics.max_drawdown_pct * 0.08 - trade_penalty - pair_penalty
        trials.append(
            {
                "params": params.to_dict(),
                "score": round(score, 4),
                "active_pairs": active_pairs,
                "metrics": metrics.to_dict(),
            }
        )

    trials.sort(key=lambda item: (item["score"], item["metrics"]["net_r"], item["metrics"]["trades"]), reverse=True)
    if not trials:
        return base, []
    return StrategyParams(**trials[0]["params"]), trials[:12]


def run_backtest(
    *,
    pairs: list[str],
    months: int,
    interval: str,
    params: StrategyParams,
    optimize: bool,
    min_trades: int,
    start_balance: float,
) -> dict[str, Any]:
    generated_at = utc_now()
    loads = [load_pair_data(pair, months=months, interval=interval) for pair in pairs]
    bars_by_pair = {item.pair: item.bars for item in loads if item.bars}
    errors = [error for item in loads for error in item.errors]

    selected_params = params
    optimizer_trials: list[dict[str, Any]] = []
    if optimize and bars_by_pair:
        selected_params, optimizer_trials = optimize_params(
            bars_by_pair,
            params,
            start_balance=start_balance,
            min_trades=min_trades,
        )

    pair_results: list[PairBacktest] = []
    for load in loads:
        if not load.bars:
            empty_metrics = summarize_trades([], start_balance=start_balance, risk_per_trade=selected_params.risk_per_trade)
            pair_results.append(
                PairBacktest(
                    pair=load.pair,
                    metrics=empty_metrics,
                    trades=[],
                    last_signal=None,
                    data_quality=load.to_quality_dict(),
                )
            )
            continue
        result = backtest_pair(load.pair, load.bars, selected_params, start_balance=start_balance)
        quality = load.to_quality_dict()
        pair_results.append(
            PairBacktest(
                pair=result.pair,
                metrics=result.metrics,
                trades=result.trades,
                last_signal=result.last_signal,
                data_quality=quality,
            )
        )

    all_trades = [trade for result in pair_results for trade in result.trades]
    portfolio_metrics = summarize_trades(
        all_trades,
        start_balance=start_balance,
        risk_per_trade=selected_params.risk_per_trade,
    )

    return {
        "generated_at_utc": generated_at.isoformat(),
        "mode": "paper_backtest",
        "months": months,
        "interval": interval,
        "pairs": pairs,
        "selected_params": selected_params.to_dict(),
        "optimized": optimize,
        "optimizer_top_trials": optimizer_trials,
        "start_balance": start_balance,
        "portfolio_metrics": portfolio_metrics.to_dict(),
        "pair_results": [result.to_dict() for result in pair_results],
        "data_errors": errors,
        "disclaimer": (
            "Research and paper-trading only. Historical backtests, especially optimized "
            "in-sample results, do not guarantee future profitability and are not financial advice."
        ),
    }


def write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "fx_smc_robot_backtest.json"
    md_path = output_dir / "fx_smc_robot_backtest.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(build_markdown_report(payload), encoding="utf-8")
    return json_path, md_path


def build_markdown_report(payload: dict[str, Any]) -> str:
    metrics = payload["portfolio_metrics"]
    params = payload["selected_params"]
    lines = [
        "# FX SMC Paper Robot - Three-Month Backtest",
        "",
        f"Generated (UTC): {payload['generated_at_utc']}",
        f"Pairs: {', '.join(payload['pairs'])}",
        f"Lookback window: {payload['months']} months",
        f"Bar interval: {payload['interval']}",
        f"Optimization enabled: {payload['optimized']}",
        "",
        "## Safety Notice",
        "",
        "This is a research/paper-trading robot. It does not connect to a broker or place live orders.",
        "Backtest performance does not guarantee future profitability and is not financial advice.",
        "",
        "## Selected Robot Profile",
        "",
        f"- Name: `{params['name']}`",
        f"- Liquidity lookback: {params['lookback_bars']} bars",
        f"- Risk/reward target: {params['rr']}:1",
        f"- Max hold: {params['max_hold_bars']} bars",
        f"- Min signal score: {params['min_score']}",
        f"- Risk per trade: {params['risk_per_trade'] * 100:.2f}%",
        f"- Session filter: {params['session_start_utc']:02d}:00-{params['session_end_utc']:02d}:00 UTC",
        "",
        "## Portfolio Result",
        "",
        f"- Trades: **{metrics['trades']}**",
        f"- Win rate: **{_pct(metrics['win_rate'])}**",
        f"- Net R: **{metrics['net_r']:.2f}R**",
        f"- Average R/trade: **{metrics['average_r']:.3f}R**",
        f"- Profit factor: **{_fmt(metrics['profit_factor'])}**",
        f"- Return at configured risk: **{metrics['return_pct']:.2f}%**",
        f"- Max drawdown: **{metrics['max_drawdown_pct']:.2f}%**",
        "",
        "## Pair Breakdown",
        "",
        "| Pair | Bars | Trades | Win Rate | Net R | Return | Max DD | Profit Factor |",
        "|------|------|--------|----------|-------|--------|--------|---------------|",
    ]

    for result in payload["pair_results"]:
        pair_metrics = result["metrics"]
        quality = result["data_quality"]
        lines.append(
            "| {pair} | {bars} | {trades} | {win_rate} | {net_r:.2f}R | {ret:.2f}% | "
            "{dd:.2f}% | {pf} |".format(
                pair=result["pair"],
                bars=quality.get("bars", 0),
                trades=pair_metrics["trades"],
                win_rate=_pct(pair_metrics["win_rate"]),
                net_r=pair_metrics["net_r"],
                ret=pair_metrics["return_pct"],
                dd=pair_metrics["max_drawdown_pct"],
                pf=_fmt(pair_metrics["profit_factor"]),
            )
        )

    lines.extend(["", "## Recent Trade Samples", ""])
    all_trades = [
        trade
        for result in payload["pair_results"]
        for trade in result["trades"]
    ]
    all_trades.sort(key=lambda item: item["exit_time"], reverse=True)
    if not all_trades:
        lines.append("No trades were triggered by the selected profile.")
    for trade in all_trades[:12]:
        lines.append(
            "- {pair} {side} entry {entry_time} exit {exit_time}: {r:.2f}R via {reason} "
            "(score {score:.2f})".format(
                pair=trade["pair"],
                side=trade["side"],
                entry_time=trade["entry_time"],
                exit_time=trade["exit_time"],
                r=trade["r_multiple"],
                reason=trade["exit_reason"],
                score=trade["score"],
            )
        )

    lines.extend(["", "## Latest Candidate Signals By Pair", ""])
    for result in payload["pair_results"]:
        signal = result.get("last_signal")
        if not signal:
            lines.append(f"- {result['pair']}: no qualifying signal in the backtest window.")
            continue
        lines.append(
            "- {pair}: last {side} signal at {time}, entry {entry:.5f}, stop {stop:.5f}, "
            "target {target:.5f}, score {score:.2f}".format(
                pair=result["pair"],
                side=signal["side"],
                time=signal["signal_time"],
                entry=signal["entry"],
                stop=signal["stop"],
                target=signal["target"],
                score=signal["score"],
            )
        )

    if payload.get("optimizer_top_trials"):
        lines.extend(["", "## Optimizer Top Trials", ""])
        lines.append("| Rank | Profile | Trades | Net R | Return | Max DD | Score |")
        lines.append("|------|---------|--------|-------|--------|--------|-------|")
        for rank, trial in enumerate(payload["optimizer_top_trials"][:8], start=1):
            trial_metrics = trial["metrics"]
            lines.append(
                f"| {rank} | `{trial['params']['name']}` | {trial_metrics['trades']} | "
                f"{trial_metrics['net_r']:.2f}R | {trial_metrics['return_pct']:.2f}% | "
                f"{trial_metrics['max_drawdown_pct']:.2f}% | {trial['score']:.2f} |"
            )

    if payload.get("data_errors"):
        lines.extend(["", "## Data Warnings", ""])
        for error in payload["data_errors"]:
            lines.append(f"- {error}")

    lines.extend(
        [
            "",
            "## How To Re-run",
            "",
            "```bash",
            "python3 scripts/fx_smc_robot_backtest.py --months 3 --interval 1h --optimize",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    if math.isinf(value):
        return "inf"
    return f"{value:.2f}"


def parse_pairs(values: list[str] | None) -> list[str]:
    if not values:
        return list(POPULAR_FX_PAIRS)
    pairs: list[str] = []
    for raw in values:
        for item in raw.split(","):
            pair = item.strip().upper().replace("/", "")
            if not pair:
                continue
            if pair not in POPULAR_FX_PAIRS:
                raise SystemExit(f"Unsupported pair '{item}'. Supported: {', '.join(POPULAR_FX_PAIRS)}")
            pairs.append(pair)
    return list(dict.fromkeys(pairs))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SMC-style FX paper robot backtester")
    parser.add_argument("--pairs", nargs="*", default=None, help="FX pairs, e.g. EURUSD GBPUSD or EURUSD,GBPUSD")
    parser.add_argument("--months", type=int, default=3, help="Backtest lookback in months")
    parser.add_argument("--interval", default="1h", help="Yahoo bar interval, e.g. 1h or 1d")
    parser.add_argument("--output-dir", default="reports/fx_trading", help="Report output directory")
    parser.add_argument("--start-balance", type=float, default=10_000.0, help="Starting paper balance")
    parser.add_argument("--risk-per-trade", type=float, default=0.01, help="Fractional risk per trade")
    parser.add_argument("--lookback-bars", type=int, default=24, help="Liquidity sweep lookback")
    parser.add_argument("--rr", type=float, default=1.5, help="Risk/reward target")
    parser.add_argument("--max-hold-bars", type=int, default=24, help="Maximum bars to hold a trade")
    parser.add_argument("--min-score", type=float, default=0.64, help="Minimum signal score")
    parser.add_argument("--session-start-utc", type=int, default=6, help="Earliest signal hour UTC")
    parser.add_argument("--session-end-utc", type=int, default=17, help="Latest signal hour UTC")
    parser.add_argument("--optimize", action="store_true", help="Run a small in-sample parameter search")
    parser.add_argument("--min-trades", type=int, default=20, help="Optimizer soft minimum trade count")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pairs = parse_pairs(args.pairs)
    params = StrategyParams(
        name="smc_liquidity_sweep_reclaim",
        lookback_bars=args.lookback_bars,
        rr=args.rr,
        max_hold_bars=args.max_hold_bars,
        min_score=args.min_score,
        session_start_utc=args.session_start_utc,
        session_end_utc=args.session_end_utc,
        risk_per_trade=args.risk_per_trade,
    )
    payload = run_backtest(
        pairs=pairs,
        months=args.months,
        interval=args.interval,
        params=params,
        optimize=args.optimize,
        min_trades=args.min_trades,
        start_balance=args.start_balance,
    )
    json_path, md_path = write_reports(payload, Path(args.output_dir))
    metrics = payload["portfolio_metrics"]
    print("FX SMC paper robot backtest complete")
    print(f"Reports: {json_path} | {md_path}")
    print(
        "Portfolio: trades={trades} win_rate={win_rate} net_r={net_r:.2f} "
        "return={ret:.2f}% max_dd={dd:.2f}%".format(
            trades=metrics["trades"],
            win_rate=_pct(metrics["win_rate"]),
            net_r=metrics["net_r"],
            ret=metrics["return_pct"],
            dd=metrics["max_drawdown_pct"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
