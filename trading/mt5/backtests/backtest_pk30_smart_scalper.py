#!/usr/bin/env python3
"""Dukascopy tick-data backtest for PedramKamangar_30s_SmartScalper.mq5.

The MT5 Strategy Tester remains the source of truth for broker execution.
This script is a portable approximation for environments without MT5.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import json
import lzma
import math
import statistics
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DUKASCOPY_URL = "https://datafeed.dukascopy.com/datafeed/{symbol}/{year}/{month}/{day}/{hour}h_ticks.bi5"
USER_AGENT = "Mozilla/5.0 (compatible; PK30SmartScalperBacktest/1.0)"


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    price_factor: float
    point: float
    contract_size: float
    quote_currency: str


SYMBOL_SPECS = {
    "EURUSD": SymbolSpec("EURUSD", 100000.0, 0.00001, 100000.0, "USD"),
    "GBPUSD": SymbolSpec("GBPUSD", 100000.0, 0.00001, 100000.0, "USD"),
    "USDJPY": SymbolSpec("USDJPY", 1000.0, 0.001, 100000.0, "JPY"),
    "EURJPY": SymbolSpec("EURJPY", 1000.0, 0.001, 100000.0, "JPY"),
    "XAUUSD": SymbolSpec("XAUUSD", 1000.0, 0.001, 100.0, "USD"),
}


@dataclass
class Tick:
    at: dt.datetime
    bid: float
    ask: float


@dataclass
class Bar:
    start: dt.datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class Position:
    side: int
    lot: float
    open_price: float
    open_time: dt.datetime
    sl: float
    tp: float
    volume: float
    realized_pnl: float = 0.0
    stage: int = 0


@dataclass
class Trade:
    symbol: str
    side: str
    opened_at: str
    closed_at: str
    lot: float
    pnl: float
    close_reason: str
    loss_streak_after: int


@dataclass
class BacktestConfig:
    initial_equity: float = 1000.0
    base_lot: float = 0.01
    max_lot: float = 1.0
    recovery_multiplier: float = 2.0
    max_recovery_steps: int = 3
    scalp_window_seconds: int = 30
    max_hold_seconds: int = 30
    min_seconds_after_close: int = 8
    trend_fast_ema: int = 21
    trend_slow_ema: int = 55
    entry_ema: int = 9
    adx_period: int = 14
    min_adx: float = 18.0
    rsi_period: int = 14
    buy_rsi_min: float = 52.0
    buy_rsi_max: float = 72.0
    sell_rsi_min: float = 28.0
    sell_rsi_max: float = 48.0
    atr_period: int = 14
    stop_atr_multiplier: float = 1.35
    tp1_atr_multiplier: float = 0.55
    tp2_atr_multiplier: float = 0.95
    tp3_atr_multiplier: float = 1.55
    trail_atr_multiplier: float = 0.75
    breakeven_buffer_points: float = 8.0
    tp1_close_percent: float = 33.0
    tp2_close_percent: float = 50.0
    max_spread_points: int = 28
    max_daily_loss_percent: float = 5.0
    max_drawdown_percent: float = 12.0
    jpy_per_usd: float = 160.0
    commission_per_lot_round_turn: float = 0.0


class Ema:
    def __init__(self, period: int) -> None:
        self.period = period
        self.multiplier = 2.0 / (period + 1.0)
        self.value: float | None = None
        self.history: list[float] = []

    def update(self, close: float) -> float:
        if self.value is None:
            self.value = close
        else:
            self.value = close * self.multiplier + self.value * (1.0 - self.multiplier)
        self.history.append(self.value)
        if len(self.history) > 5:
            self.history.pop(0)
        return self.value


class Atr:
    def __init__(self, period: int) -> None:
        self.period = period
        self.prev_close: float | None = None
        self.value: float | None = None
        self.tr_values: list[float] = []

    def update(self, bar: Bar) -> float | None:
        if self.prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(bar.high - bar.low, abs(bar.high - self.prev_close), abs(bar.low - self.prev_close))

        self.prev_close = bar.close
        if self.value is None:
            self.tr_values.append(tr)
            if len(self.tr_values) < self.period:
                return None
            self.value = sum(self.tr_values[-self.period :]) / self.period
        else:
            self.value = ((self.value * (self.period - 1)) + tr) / self.period
        return self.value


class Rsi:
    def __init__(self, period: int) -> None:
        self.period = period
        self.prev_close: float | None = None
        self.avg_gain: float | None = None
        self.avg_loss: float | None = None
        self.gains: list[float] = []
        self.losses: list[float] = []
        self.value: float | None = None

    def update(self, close: float) -> float | None:
        if self.prev_close is None:
            self.prev_close = close
            return None

        change = close - self.prev_close
        self.prev_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self.avg_gain is None or self.avg_loss is None:
            self.gains.append(gain)
            self.losses.append(loss)
            if len(self.gains) < self.period:
                return None
            self.avg_gain = sum(self.gains[-self.period :]) / self.period
            self.avg_loss = sum(self.losses[-self.period :]) / self.period
        else:
            self.avg_gain = ((self.avg_gain * (self.period - 1)) + gain) / self.period
            self.avg_loss = ((self.avg_loss * (self.period - 1)) + loss) / self.period

        if self.avg_loss == 0.0:
            self.value = 100.0
        else:
            rs = self.avg_gain / self.avg_loss
            self.value = 100.0 - (100.0 / (1.0 + rs))
        return self.value


class Adx:
    def __init__(self, period: int) -> None:
        self.period = period
        self.prev_bar: Bar | None = None
        self.tr_smooth: float | None = None
        self.plus_dm_smooth: float | None = None
        self.minus_dm_smooth: float | None = None
        self.seed_tr: list[float] = []
        self.seed_plus_dm: list[float] = []
        self.seed_minus_dm: list[float] = []
        self.dx_values: list[float] = []
        self.value: float | None = None

    def update(self, bar: Bar) -> float | None:
        if self.prev_bar is None:
            self.prev_bar = bar
            return None

        up_move = bar.high - self.prev_bar.high
        down_move = self.prev_bar.low - bar.low
        plus_dm = up_move if up_move > down_move and up_move > 0.0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0.0 else 0.0
        tr = max(bar.high - bar.low, abs(bar.high - self.prev_bar.close), abs(bar.low - self.prev_bar.close))
        self.prev_bar = bar

        if self.tr_smooth is None or self.plus_dm_smooth is None or self.minus_dm_smooth is None:
            self.seed_tr.append(tr)
            self.seed_plus_dm.append(plus_dm)
            self.seed_minus_dm.append(minus_dm)
            if len(self.seed_tr) < self.period:
                return None
            self.tr_smooth = sum(self.seed_tr[-self.period :])
            self.plus_dm_smooth = sum(self.seed_plus_dm[-self.period :])
            self.minus_dm_smooth = sum(self.seed_minus_dm[-self.period :])
        else:
            self.tr_smooth = self.tr_smooth - (self.tr_smooth / self.period) + tr
            self.plus_dm_smooth = self.plus_dm_smooth - (self.plus_dm_smooth / self.period) + plus_dm
            self.minus_dm_smooth = self.minus_dm_smooth - (self.minus_dm_smooth / self.period) + minus_dm

        if self.tr_smooth == 0.0:
            return None

        plus_di = 100.0 * (self.plus_dm_smooth / self.tr_smooth)
        minus_di = 100.0 * (self.minus_dm_smooth / self.tr_smooth)
        di_sum = plus_di + minus_di
        if di_sum == 0.0:
            return None

        dx = 100.0 * abs(plus_di - minus_di) / di_sum
        if self.value is None:
            self.dx_values.append(dx)
            if len(self.dx_values) < self.period:
                return None
            self.value = sum(self.dx_values[-self.period :]) / self.period
        else:
            self.value = ((self.value * (self.period - 1)) + dx) / self.period
        return self.value


class BarAggregator:
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        self.current: Bar | None = None

    def update(self, tick_time: dt.datetime, price: float) -> Bar | None:
        bucket = floor_time(tick_time, self.seconds)
        if self.current is None:
            self.current = Bar(bucket, price, price, price, price)
            return None

        if bucket == self.current.start:
            self.current.high = max(self.current.high, price)
            self.current.low = min(self.current.low, price)
            self.current.close = price
            return None

        closed = self.current
        self.current = Bar(bucket, price, price, price, price)
        return closed


class SmartScalperBacktest:
    def __init__(self, symbol: str, spec: SymbolSpec, config: BacktestConfig) -> None:
        self.symbol = symbol
        self.spec = spec
        self.config = config
        self.equity = config.initial_equity
        self.peak_equity = config.initial_equity
        self.max_drawdown = 0.0
        self.day_code: str | None = None
        self.day_start_equity = config.initial_equity
        self.loss_streak = 0
        self.last_close_time: dt.datetime | None = None
        self.next_cycle: dt.datetime | None = None
        self.position: Position | None = None
        self.trades: list[Trade] = []
        self.equity_curve: list[float] = [config.initial_equity]

        self.m1 = BarAggregator(60)
        self.m5 = BarAggregator(300)
        self.entry_ema = Ema(config.entry_ema)
        self.trend_fast = Ema(config.trend_fast_ema)
        self.trend_slow = Ema(config.trend_slow_ema)
        self.atr = Atr(config.atr_period)
        self.rsi = Rsi(config.rsi_period)
        self.adx = Adx(config.adx_period)

    def on_tick(self, tick: Tick) -> None:
        closed_m1 = self.m1.update(tick.at, tick.bid)
        if closed_m1:
            self.entry_ema.update(closed_m1.close)
            self.atr.update(closed_m1)
            self.rsi.update(closed_m1.close)

        closed_m5 = self.m5.update(tick.at, tick.bid)
        if closed_m5:
            self.trend_fast.update(closed_m5.close)
            self.trend_slow.update(closed_m5.close)
            self.adx.update(closed_m5)

        self.manage_position(tick)

        if self.next_cycle is None:
            self.next_cycle = floor_time(tick.at, self.config.scalp_window_seconds)

        while self.next_cycle is not None and tick.at >= self.next_cycle:
            self.evaluate_cycle(self.next_cycle, tick)
            self.next_cycle += dt.timedelta(seconds=self.config.scalp_window_seconds)

    def evaluate_cycle(self, cycle_time: dt.datetime, tick: Tick) -> None:
        if self.position is not None:
            return
        if self.last_close_time and (cycle_time - self.last_close_time).total_seconds() < self.config.min_seconds_after_close:
            return
        if not self.risk_guards_allow_entry(cycle_time):
            return
        if self.indicators_not_ready():
            return
        if self.spread_points(tick) > self.config.max_spread_points:
            return

        trend = self.detect_trend()
        if trend == 0:
            return
        if not self.entry_filter_allows(trend, tick):
            return

        self.open_position(trend, tick)

    def risk_guards_allow_entry(self, cycle_time: dt.datetime) -> bool:
        day_code = cycle_time.date().isoformat()
        if self.day_code != day_code:
            self.day_code = day_code
            self.day_start_equity = self.equity

        if self.day_start_equity > 0.0 and self.config.max_daily_loss_percent > 0.0:
            daily_loss_percent = 100.0 * (self.day_start_equity - self.equity) / self.day_start_equity
            if daily_loss_percent >= self.config.max_daily_loss_percent:
                return False

        if self.peak_equity > 0.0 and self.config.max_drawdown_percent > 0.0:
            drawdown_percent = 100.0 * (self.peak_equity - self.equity) / self.peak_equity
            if drawdown_percent >= self.config.max_drawdown_percent:
                return False

        return True

    def indicators_not_ready(self) -> bool:
        return (
            self.atr.value is None
            or self.rsi.value is None
            or self.adx.value is None
            or self.entry_ema.value is None
            or self.trend_fast.value is None
            or self.trend_slow.value is None
            or len(self.trend_fast.history) < 3
        )

    def detect_trend(self) -> int:
        assert self.adx.value is not None
        fast = self.trend_fast.history
        slow = self.trend_slow.value
        if slow is None or self.adx.value < self.config.min_adx:
            return 0

        fast_rising = fast[-1] > fast[-2] and fast[-2] >= fast[-3]
        fast_falling = fast[-1] < fast[-2] and fast[-2] <= fast[-3]
        if fast[-1] > slow and fast_rising:
            return 1
        if fast[-1] < slow and fast_falling:
            return -1
        return 0

    def entry_filter_allows(self, trend: int, tick: Tick) -> bool:
        assert self.entry_ema.value is not None
        assert self.rsi.value is not None
        if trend == 1:
            return tick.ask > self.entry_ema.value and self.config.buy_rsi_min <= self.rsi.value <= self.config.buy_rsi_max
        return tick.bid < self.entry_ema.value and self.config.sell_rsi_min <= self.rsi.value <= self.config.sell_rsi_max

    def open_position(self, trend: int, tick: Tick) -> None:
        assert self.atr.value is not None
        lot = self.next_lot()
        stop_distance = self.smart_stop_distance(tick)
        tp_distance = self.atr.value * self.config.tp3_atr_multiplier
        price = tick.ask if trend == 1 else tick.bid
        sl = price - stop_distance if trend == 1 else price + stop_distance
        tp = price + tp_distance if trend == 1 else price - tp_distance
        self.position = Position(trend, lot, price, tick.at, sl, tp, lot)

    def manage_position(self, tick: Tick) -> None:
        pos = self.position
        if pos is None or self.atr.value is None:
            return

        market = tick.bid if pos.side == 1 else tick.ask
        profit_distance = market - pos.open_price if pos.side == 1 else pos.open_price - market

        if pos.side == 1 and tick.bid <= pos.sl:
            self.close_position(tick, pos.sl, "stop_loss")
            return
        if pos.side == -1 and tick.ask >= pos.sl:
            self.close_position(tick, pos.sl, "stop_loss")
            return
        if pos.side == 1 and tick.bid >= pos.tp:
            self.close_position(tick, pos.tp, "tp3")
            return
        if pos.side == -1 and tick.ask <= pos.tp:
            self.close_position(tick, pos.tp, "tp3")
            return

        tp1_distance = self.atr.value * self.config.tp1_atr_multiplier
        tp2_distance = self.atr.value * self.config.tp2_atr_multiplier

        if pos.stage < 1 and profit_distance >= tp1_distance:
            self.partial_close(tick, self.config.tp1_close_percent)
            self.move_stop_to_breakeven()
            if self.position:
                self.position.stage = 1

        if self.position and self.position.stage < 2 and profit_distance >= tp2_distance:
            self.partial_close(tick, self.config.tp2_close_percent)
            self.lock_profit_stop()
            if self.position:
                self.position.stage = 2

        if self.position and self.position.stage >= 2:
            self.trail_stop(tick)

        if self.position and (tick.at - self.position.open_time).total_seconds() >= self.config.max_hold_seconds:
            exit_price = tick.bid if self.position.side == 1 else tick.ask
            self.close_position(tick, exit_price, "time_exit")

    def partial_close(self, tick: Tick, percent: float) -> None:
        pos = self.position
        if pos is None:
            return
        close_volume = normalize_volume(pos.volume * percent / 100.0)
        if close_volume < 0.01 or (pos.volume - close_volume) < 0.01:
            return
        exit_price = tick.bid if pos.side == 1 else tick.ask
        pnl = self.pnl_usd(pos.side, pos.open_price, exit_price, close_volume)
        pnl -= self.commission(close_volume, half_turn=True)
        pos.realized_pnl += pnl
        pos.volume = normalize_volume(pos.volume - close_volume)

    def move_stop_to_breakeven(self) -> None:
        pos = self.position
        if pos is None:
            return
        buffer = self.config.breakeven_buffer_points * self.spec.point
        new_sl = pos.open_price + buffer if pos.side == 1 else pos.open_price - buffer
        self.modify_stop_if_better(new_sl)

    def lock_profit_stop(self) -> None:
        pos = self.position
        if pos is None or self.atr.value is None:
            return
        lock_distance = self.atr.value * max(self.config.tp1_atr_multiplier * 0.50, 0.20)
        new_sl = pos.open_price + lock_distance if pos.side == 1 else pos.open_price - lock_distance
        self.modify_stop_if_better(new_sl)

    def trail_stop(self, tick: Tick) -> None:
        pos = self.position
        if pos is None or self.atr.value is None:
            return
        trail_distance = max(self.atr.value * self.config.trail_atr_multiplier, self.smart_stop_distance(tick) * 0.35)
        new_sl = tick.bid - trail_distance if pos.side == 1 else tick.ask + trail_distance
        self.modify_stop_if_better(new_sl)

    def modify_stop_if_better(self, new_sl: float) -> None:
        pos = self.position
        if pos is None:
            return
        if pos.side == 1 and new_sl > pos.sl + self.spec.point:
            pos.sl = new_sl
        elif pos.side == -1 and new_sl < pos.sl - self.spec.point:
            pos.sl = new_sl

    def close_position(self, tick: Tick, exit_price: float, reason: str) -> None:
        pos = self.position
        if pos is None:
            return
        pnl = pos.realized_pnl + self.pnl_usd(pos.side, pos.open_price, exit_price, pos.volume)
        pnl -= self.commission(pos.lot, half_turn=False)
        self.equity += pnl
        self.equity_curve.append(self.equity)
        self.peak_equity = max(self.peak_equity, self.equity)
        if self.peak_equity > 0.0:
            self.max_drawdown = max(self.max_drawdown, 100.0 * (self.peak_equity - self.equity) / self.peak_equity)

        if pnl > 0.0:
            self.loss_streak = 0
        elif pnl < 0.0:
            self.loss_streak = min(self.loss_streak + 1, self.config.max_recovery_steps)

        self.trades.append(
            Trade(
                symbol=self.symbol,
                side="BUY" if pos.side == 1 else "SELL",
                opened_at=pos.open_time.isoformat(),
                closed_at=tick.at.isoformat(),
                lot=pos.lot,
                pnl=pnl,
                close_reason=reason,
                loss_streak_after=self.loss_streak,
            )
        )
        self.last_close_time = tick.at
        self.position = None

    def pnl_usd(self, side: int, open_price: float, exit_price: float, lot: float) -> float:
        quote_pnl = (exit_price - open_price) * lot * self.spec.contract_size
        if side == -1:
            quote_pnl *= -1.0
        if self.spec.quote_currency == "USD":
            return quote_pnl
        if self.symbol == "USDJPY":
            return quote_pnl / max(exit_price, 1e-9)
        return quote_pnl / self.config.jpy_per_usd

    def commission(self, lot: float, half_turn: bool) -> float:
        commission = self.config.commission_per_lot_round_turn * lot
        return commission / 2.0 if half_turn else commission / 2.0

    def spread_points(self, tick: Tick) -> float:
        return (tick.ask - tick.bid) / self.spec.point

    def smart_stop_distance(self, tick: Tick) -> float:
        assert self.atr.value is not None
        broker_min = ((self.spread_points(tick) + 3.0) * self.spec.point)
        atr_stop = self.atr.value * self.config.stop_atr_multiplier
        return max(atr_stop, broker_min)

    def next_lot(self) -> float:
        step = min(max(self.loss_streak, 0), self.config.max_recovery_steps)
        lot = self.config.base_lot * (self.config.recovery_multiplier**step)
        return normalize_volume(min(lot, self.config.max_lot))

    def summary(self) -> dict[str, object]:
        wins = [t for t in self.trades if t.pnl > 0.0]
        losses = [t for t in self.trades if t.pnl < 0.0]
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else None
        returns = [self.equity_curve[i] - self.equity_curve[i - 1] for i in range(1, len(self.equity_curve))]
        return {
            "symbol": self.symbol,
            "initial_equity": round(self.config.initial_equity, 2),
            "final_equity": round(self.equity, 2),
            "net_profit": round(self.equity - self.config.initial_equity, 2),
            "return_percent": round(100.0 * (self.equity - self.config.initial_equity) / self.config.initial_equity, 2),
            "trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_percent": round(100.0 * len(wins) / len(self.trades), 2) if self.trades else 0.0,
            "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
            "max_drawdown_percent": round(self.max_drawdown, 2),
            "max_recovery_step": max((t.loss_streak_after for t in self.trades), default=0),
            "avg_trade_pnl": round(statistics.mean(returns), 4) if returns else 0.0,
        }


def normalize_volume(volume: float) -> float:
    volume = max(0.01, volume)
    return round(math.floor((volume - 0.01) / 0.01 + 1e-9) * 0.01 + 0.01, 2)


def floor_time(value: dt.datetime, seconds: int) -> dt.datetime:
    timestamp = int(value.replace(tzinfo=dt.timezone.utc).timestamp())
    return dt.datetime.fromtimestamp(timestamp - (timestamp % seconds), tz=dt.timezone.utc).replace(tzinfo=None)


def iter_hours(start: dt.datetime, end: dt.datetime) -> Iterable[dt.datetime]:
    cursor = floor_time(start, 3600)
    while cursor < end:
        yield cursor
        cursor += dt.timedelta(hours=1)


def dukascopy_cache_path(cache_dir: Path, symbol: str, hour: dt.datetime) -> Path:
    return cache_dir / symbol / f"{hour.year}" / f"{hour.month:02d}" / f"{hour.day:02d}" / f"{hour.hour:02d}h_ticks.bi5"


def download_hour(cache_dir: Path, symbol: str, hour: dt.datetime, retries: int = 3) -> tuple[dt.datetime, Path | None, str]:
    path = dukascopy_cache_path(cache_dir, symbol, hour)
    if path.exists() and path.stat().st_size > 0:
        return hour, path, "cached"

    path.parent.mkdir(parents=True, exist_ok=True)
    url = DUKASCOPY_URL.format(
        symbol=symbol,
        year=hour.year,
        month=f"{hour.month - 1:02d}",
        day=f"{hour.day:02d}",
        hour=f"{hour.hour:02d}",
    )
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                raw = response.read()
            if not raw:
                return hour, None, "empty"
            path.write_bytes(raw)
            return hour, path, "downloaded"
        except HTTPError as exc:
            if exc.code == 404:
                return hour, None, "missing"
            if attempt + 1 == retries:
                return hour, None, f"http_{exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            if attempt + 1 == retries:
                return hour, None, type(exc).__name__
        time.sleep(0.7 * (attempt + 1))
    return hour, None, "failed"


def ensure_symbol_data(cache_dir: Path, symbol: str, start: dt.datetime, end: dt.datetime, workers: int) -> list[Path]:
    hours = list(iter_hours(start, end))
    paths: list[Path] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(download_hour, cache_dir, symbol, hour) for hour in hours]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            hour, path, status = future.result()
            if path:
                paths.append(path)
            if index % 250 == 0 or index == len(futures):
                print(f"{symbol}: data {index}/{len(futures)} hours processed, latest {hour} ({status})", file=sys.stderr)
    return sorted(paths)


def read_ticks(path: Path, spec: SymbolSpec, hour: dt.datetime, start: dt.datetime, end: dt.datetime) -> Iterable[Tick]:
    try:
        raw = path.read_bytes()
        data = lzma.decompress(raw, format=lzma.FORMAT_ALONE)
    except (OSError, lzma.LZMAError):
        return

    record_size = 20
    for offset in range(0, len(data) - record_size + 1, record_size):
        millisecond, ask_raw, bid_raw, _ask_volume, _bid_volume = struct.unpack(">IIIff", data[offset : offset + record_size])
        at = hour + dt.timedelta(milliseconds=millisecond)
        if at < start or at >= end:
            continue
        yield Tick(at=at, bid=bid_raw / spec.price_factor, ask=ask_raw / spec.price_factor)


def run_symbol(symbol: str, start: dt.datetime, end: dt.datetime, cache_dir: Path, workers: int, config: BacktestConfig) -> tuple[dict[str, object], list[Trade]]:
    spec = SYMBOL_SPECS[symbol]
    print(f"{symbol}: downloading/caching real tick data...", file=sys.stderr)
    paths = ensure_symbol_data(cache_dir, symbol, start, end, workers)
    tester = SmartScalperBacktest(symbol, spec, config)
    print(f"{symbol}: running backtest over {len(paths)} hourly files...", file=sys.stderr)
    for path in paths:
        parts = path.parts
        hour = dt.datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(parts[-1][:2]))
        for tick in read_ticks(path, spec, hour, start, end):
            tester.on_tick(tick)
    return tester.summary(), tester.trades


def parse_dt(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def write_outputs(output_dir: Path, results: list[dict[str, object]], trades: list[Trade], metadata: dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pk30_backtest_summary.json").write_text(json.dumps({"metadata": metadata, "results": results}, indent=2), encoding="utf-8")

    with (output_dir / "pk30_backtest_trades.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Trade.__dataclass_fields__.keys()), lineterminator="\n")
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.__dict__)

    lines = [
        "# PK30 SmartScalper Real Tick Backtest",
        "",
        f"- Data source: Dukascopy real tick bid/ask data",
        f"- Start: `{metadata['start']}`",
        f"- End: `{metadata['end']}`",
        f"- Initial equity: `{metadata['initial_equity']}` USD",
        f"- Commission model: `{metadata['commission_per_lot_round_turn']}` USD per lot round turn",
        f"- Note: portable Python approximation of the MT5 EA; MT5 Strategy Tester on BazarnForex remains the broker-accurate reference.",
        "",
        "| Symbol | Final equity | Net profit | Return % | Trades | Win rate % | Profit factor | Max DD % | Max recovery |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        row = dict(result)
        row["profit_factor"] = row["profit_factor"] if row["profit_factor"] is not None else "n/a"
        lines.append(
            "| {symbol} | {final_equity:.2f} | {net_profit:.2f} | {return_percent:.2f} | {trades} | {win_rate_percent:.2f} | {profit_factor} | {max_drawdown_percent:.2f} | {max_recovery_step} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Default EA settings were used unless noted in metadata.")
    lines.append("- JPY cross PnL that is not USDJPY is converted with the configured JPY/USD reference rate.")
    lines.append("- Results include real spread from bid/ask ticks, but not BazarnForex slippage, rejected orders, swaps, or broker-specific stop/freeze behavior.")
    (output_dir / "PK30_REAL_TICK_BACKTEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["EURUSD", "USDJPY", "GBPUSD", "EURJPY", "XAUUSD"])
    parser.add_argument("--start", default="2026-04-01T00:00:00")
    parser.add_argument("--end", default="2026-07-01T12:00:00")
    parser.add_argument("--initial-equity", type=float, default=1000.0)
    parser.add_argument("--cache-dir", type=Path, default=Path("/tmp/pk30_dukascopy_cache"))
    parser.add_argument("--output-dir", type=Path, default=Path("trading/mt5/reports/pk30_real_tick_backtest"))
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--commission-per-lot-round-turn", type=float, default=0.0)
    parser.add_argument("--jpy-per-usd", type=float, default=160.0)
    args = parser.parse_args()

    start = parse_dt(args.start)
    end = parse_dt(args.end)
    symbols = [symbol.upper() for symbol in args.symbols]
    unknown = [symbol for symbol in symbols if symbol not in SYMBOL_SPECS]
    if unknown:
        raise SystemExit(f"Unsupported symbols: {', '.join(unknown)}")

    config = BacktestConfig(
        initial_equity=args.initial_equity,
        commission_per_lot_round_turn=args.commission_per_lot_round_turn,
        jpy_per_usd=args.jpy_per_usd,
    )

    results: list[dict[str, object]] = []
    all_trades: list[Trade] = []
    for symbol in symbols:
        summary, trades = run_symbol(symbol, start, end, args.cache_dir, args.workers, config)
        results.append(summary)
        all_trades.extend(trades)
        print(json.dumps(summary, sort_keys=True), flush=True)

    results.sort(key=lambda item: float(item["net_profit"]), reverse=True)
    metadata = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_equity": args.initial_equity,
        "symbols": symbols,
        "commission_per_lot_round_turn": args.commission_per_lot_round_turn,
        "jpy_per_usd": args.jpy_per_usd,
    }
    write_outputs(args.output_dir, results, all_trades, metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
