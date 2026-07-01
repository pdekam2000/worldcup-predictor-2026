# PK30 SmartScalper Real Tick Backtest

- Data source: Dukascopy real tick bid/ask data
- Start: `2026-04-01T00:00:00`
- End: `2026-07-01T12:00:00`
- Initial equity: `1000.0` USD
- Commission model: `0.0` USD per lot round turn
- Adaptive multi-strategy: `True`; signal interval `60` seconds; max hold `14400` seconds; minimum R:R `1.6`
- Evaluated symbol profile filter: `True`
- Aggressive burst: `False`; max trades `10`; interval `5-10` seconds
- First-loss stop: `True`; cooldown `180` seconds; better-opportunity ADX bonus `8.0`
- Note: portable Python approximation of the MT5 EA; MT5 Strategy Tester on BazarnForex remains the broker-accurate reference.

| Symbol | Final equity | Net profit | Return % | Trades | Win rate % | Profit factor | Max DD % | Max recovery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 1014.03 | 14.03 | 1.40 | 70 | 62.86 | 1.501 | 0.71 | 0 |
| GBPUSD | 1004.96 | 4.96 | 0.50 | 37 | 45.95 | 1.188 | 0.94 | 0 |
| USDJPY | 1000.00 | 0.00 | 0.00 | 0 | 0.00 | n/a | 0.00 | 0 |
| EURJPY | 1000.00 | 0.00 | 0.00 | 0 | 0.00 | n/a | 0.00 | 0 |
| XAUUSD | 1000.00 | 0.00 | 0.00 | 0 | 0.00 | n/a | 0.00 | 0 |

## Interpretation

- Default EA settings were used unless noted in metadata.
- JPY cross PnL that is not USDJPY is converted with the configured JPY/USD reference rate.
- Results include real spread from bid/ask ticks, but not BazarnForex slippage, rejected orders, swaps, or broker-specific stop/freeze behavior.
