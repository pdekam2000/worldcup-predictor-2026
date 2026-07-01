# PedramKamangar 30s SmartScalper for MT5

Standalone MetaTrader 5 Expert Advisor for adaptive Forex strategy execution on BazarnForex or any MT5 broker.

> Risk warning: no Forex strategy can guarantee profit. This EA uses objective rules and risk guards, but it must be demo-tested and forward-tested before any live use.

## Files

- EA source: `trading/mt5/experts/PedramKamangar_30s_SmartScalper.mq5`
- Error log at runtime: `MQL5/Common/Files/PedramKamangar_30s_SmartScalper_errors.csv`

## Strategy summary

1. **Adaptive multi-strategy router**
   - Default mode is `InpTradingMode=MODE_ADAPTIVE_MULTI`.
   - The EA first identifies market conditions, then routes to one of five strategy families:
     - Intraday breakout on M15 ranges.
     - MACD 1-hour momentum.
     - 4-hour EMA 34/55 pullback trend strategy.
     - H1 mean reversion/range trading with RSI exhaustion.
     - H4 Donchian-style trend breakout.
   - If the market condition does not match a rule set, no trade is opened.
   - `InpUseEvaluatedSymbolProfile=true` filters strategy families per symbol based on the latest real tick-data evaluation. This reduces applying a strategy to symbols where it recently had negative expectancy, but it must be forward-tested because profiles can become overfit.
   - Current default profile: EURUSD uses Donchian/EMA/Mean Reversion; GBPUSD uses Donchian; USDJPY, EURJPY and XAUUSD are disabled until forward testing or a new optimization proves positive expectancy.

2. **Structured workflow**
   - Identify market condition.
   - Look for a matching setup.
   - Define stop and target before entry.
   - Execute only when spread/drawdown/daily-loss guards allow.
   - Record trades with strategy tags in comments and backtest CSV.

3. **Aggressive burst mode**
   - Disabled by default because the real tick-data backtest was not profitable.
   - Can still be selected with `InpTradingMode=MODE_AGGRESSIVE_BURST` or `InpAggressiveBurstMode=true`.
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
   - Default recovery is disabled with `InpRecoveryMultiplier=1.0` and `InpMaxRecoverySteps=0`.
   - If manually enabled, safety caps are `InpMaxRecoverySteps` and `InpMaxLot`.

6. **Risk/reward-aware exits**
   - Adaptive entries use `InpMinRiskReward` so the target is not smaller than the configured reward multiple of stop distance.
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
| `InpTradingMode` | `MODE_ADAPTIVE_MULTI` |
| `InpBaseLot` | `0.01` |
| `InpMaxLot` | account-dependent, start low |
| `InpRecoveryMultiplier` | `1.0` |
| `InpMaxRecoverySteps` | `0` |
| `InpMinRiskReward` | `1.60` or higher |
| `InpUseEvaluatedSymbolProfile` | `true` |
| `InpAggressiveBurstMode` | `false`; enable only after demo testing |
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
