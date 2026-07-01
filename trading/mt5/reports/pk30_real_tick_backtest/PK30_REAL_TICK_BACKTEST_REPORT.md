# PK30 SmartScalper Real Tick Backtest

- Data source: Dukascopy real tick bid/ask data
- Start: `2026-04-01T00:00:00`
- End: `2026-07-01T12:00:00`
- Initial equity: `1000.0` USD
- Commission model: `0.0` USD per lot round turn
- Aggressive burst: `True`; max trades `10`; interval `5-10` seconds
- First-loss stop: `True`; cooldown `180` seconds; better-opportunity ADX bonus `8.0`
- Note: portable Python approximation of the MT5 EA; MT5 Strategy Tester on BazarnForex remains the broker-accurate reference.

| Symbol | Final equity | Net profit | Return % | Trades | Win rate % | Profit factor | Max DD % | Max recovery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| XAUUSD | 992.90 | -7.10 | -0.71 | 1 | 0.00 | 0.0 | 0.71 | 1 |
| USDJPY | 881.45 | -118.55 | -11.85 | 486 | 23.66 | 0.284 | 12.18 | 3 |
| EURUSD | 878.66 | -121.34 | -12.13 | 607 | 28.17 | 0.332 | 12.13 | 3 |
| EURJPY | 878.33 | -121.67 | -12.17 | 344 | 18.31 | 0.132 | 12.17 | 3 |
| GBPUSD | 875.99 | -124.01 | -12.40 | 407 | 24.08 | 0.321 | 12.40 | 3 |

## Interpretation

- Default EA settings were used unless noted in metadata.
- JPY cross PnL that is not USDJPY is converted with the configured JPY/USD reference rate.
- Results include real spread from bid/ask ticks, but not BazarnForex slippage, rejected orders, swaps, or broker-specific stop/freeze behavior.
