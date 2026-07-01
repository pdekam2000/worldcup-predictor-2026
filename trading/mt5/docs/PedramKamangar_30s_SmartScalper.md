# PedramKamangar 30s SmartScalper for MT5

Standalone MetaTrader 5 Expert Advisor for 30-second trend scalping on BazarnForex or any MT5 broker.

> Risk warning: this EA uses recovery sizing after losing trades. Even with caps, this is high risk and can quickly increase drawdown during choppy markets. Test on demo first.

## Files

- EA source: `trading/mt5/experts/PedramKamangar_30s_SmartScalper.mq5`
- Error log at runtime: `MQL5/Common/Files/PedramKamangar_30s_SmartScalper_errors.csv`

## Strategy summary

1. **Trend discovery first**
   - Uses EMA 21/55 and ADX on `InpTrendTimeframe` (default `M5`).
   - Trades only in the trend direction.

2. **30-second scalping cadence**
   - MT5 standard charts do not have a native 30-second timeframe, so the EA uses a timer.
   - Every `InpScalpWindowSeconds` seconds (default `30`), it checks for a fresh trend-aligned entry.
   - `InpMaxPositionHoldSeconds` defaults to `30`, so stale scalp positions are closed by time if TP/SL does not finish first.

3. **Aggressive burst mode**
   - Enabled by default with `InpAggressiveBurstMode=true`.
   - When the EA finds a valid trend-aligned setup after activation, it can open up to `InpBurstMaxTrades=10` trades.
   - Burst entries are spaced by `InpBurstIntervalMinSec=5` to `InpBurstIntervalMaxSec=10` seconds.
   - `InpMaxConcurrentPositions=10` caps simultaneous positions for hedging accounts. On netting accounts, MT5 may merge same-symbol entries into one net position.
   - With `InpBurstStopOnFirstLoss=true`, the first final losing close stops the burst immediately.
   - After a burst loss, the EA waits `InpBurstCooldownAfterLoss=180` seconds and requires a stronger setup: ADX must exceed `InpMinAdx + InpBetterOpportunityAdxBonus`, and RSI must sit inside the tighter buffered range.

4. **Semi/full automatic mode**
   - Full auto: `InpEnableAutoTrading=true` and `InpSignalOnlyMode=false`.
   - Semi-auto/signal mode: set `InpSignalOnlyMode=true`; the EA alerts and logs signals but does not place orders.

5. **Recovery sizing**
   - Base lot: `InpBaseLot`.
   - After a losing final close, next lot = `BaseLot * 2^lossStreak`.
   - After a winning final close, lot resets to base.
   - Safety caps: `InpMaxRecoverySteps` and `InpMaxLot`.

6. **Smart three-step profit**
   - TP1: partial close and move SL to breakeven.
   - TP2: partial close and lock profit.
   - TP3: broker TP target, with smart ATR trailing after TP2.

7. **Smart stop loss**
   - Initial SL is ATR-based and also respects broker stop/freeze level plus spread.
   - Breakeven and trailing logic move SL only in the safer direction.
   - Guards stop new entries on high spread, daily loss limit, and max equity drawdown.

8. **Owner/running panel**
   - Draws a colored chart panel with:
     - `PK 30s Smart Scalper`
     - `Owner: Pedram Kamangar`
     - Broker tag
     - Running status, spread, recovery step, and next lot

## Installation

1. Open MT5.
2. Go to **File > Open Data Folder**.
3. Copy `PedramKamangar_30s_SmartScalper.mq5` to:
   - `MQL5/Experts/PedramKamangar_30s_SmartScalper.mq5`
4. Open **MetaEditor**.
5. Compile the file.
6. In MT5, attach the EA to an `M1` chart for the pair you want to test.
7. Enable **Algo Trading** only after demo testing.

## Recommended first demo settings

| Input | Conservative start |
| --- | --- |
| `InpBaseLot` | `0.01` |
| `InpMaxLot` | account-dependent, start low |
| `InpMaxRecoverySteps` | `2` or `3` |
| `InpAggressiveBurstMode` | `true` only after demo testing |
| `InpBurstMaxTrades` | `10` requested aggressive mode; reduce if drawdown is high |
| `InpBurstIntervalMinSec` / `InpBurstIntervalMaxSec` | `5` / `10` |
| `InpBurstStopOnFirstLoss` | `true` |
| `InpBurstCooldownAfterLoss` | `180` or higher |
| `InpMaxSpreadPoints` | pair-dependent; tighten for EURUSD |
| `InpMaxDailyLossPercent` | `3` to `5` |
| `InpMaxDrawdownPercent` | `8` to `12` |
| `InpSignalOnlyMode` | `true` for first live observation |

## Backtest protocol for finding the best pair

This repository environment does not include MT5, MetaEditor, Strategy Tester, or BazarnForex tick data, so a real broker backtest cannot be executed here. The EA is ready to compile and test inside MT5.

Run this exact comparison in **MT5 Strategy Tester**:

| Setting | Value |
| --- | --- |
| Expert | `PedramKamangar_30s_SmartScalper` |
| Model | `Every tick based on real ticks` |
| Period | `M1` |
| Deposit | same for every pair |
| Leverage | same as BazarnForex account |
| Date range | at least 3 recent months, then repeat on a separate out-of-sample month |
| Optimization | disabled for the first baseline |
| Spread | current broker spread or real ticks |

Test these pairs first, because 30-second scalping is most sensitive to spread and liquidity:

1. `EURUSD` - usually the first candidate because of tight spread.
2. `USDJPY` - often stable spread and good liquidity.
3. `GBPUSD` - more movement, but filter spread carefully.
4. `EURJPY` - useful trend movement; check commission/spread.
5. `XAUUSD` - only if BazarnForex spread and stop levels are low enough; volatility is high.

Rank pairs by:

- Profit factor above `1.20`
- Max drawdown below your limit
- Recovery step rarely reaching max
- Average trade duration close to 30 seconds
- Enough trades to be statistically meaningful
- Good out-of-sample performance, not only optimized history

## Backtest result template

Fill this table after Strategy Tester runs:

| Pair | Net profit | Profit factor | Max DD % | Trades | Win rate | Max recovery step | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| EURUSD | | | | | | | |
| USDJPY | | | | | | | |
| GBPUSD | | | | | | | |
| EURJPY | | | | | | | |
| XAUUSD | | | | | | | |

## Practical safety notes

- Never start on a real account with recovery sizing until demo and out-of-sample tests are acceptable.
- Avoid news windows and high-spread rollover times.
- Keep `InpMaxRecoverySteps` small; increasing it can hide risk in backtests.
- If Strategy Tester shows the EA often reaches max recovery, that pair/session is not suitable.
- Use one chart per symbol and keep `InpMagicNumber` unique if running multiple instances.
