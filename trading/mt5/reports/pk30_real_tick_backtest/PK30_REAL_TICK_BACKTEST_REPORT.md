# PK30 SmartScalper Real Tick Backtest

- Data source: Dukascopy real tick bid/ask data
- Start: `2026-04-01T00:00:00`
- End: `2026-07-01T12:00:00`
- Initial equity: `1000.0` USD
- Commission model: `0.0` USD per lot round turn
- Note: portable Python approximation of the MT5 EA; MT5 Strategy Tester on BazarnForex remains the broker-accurate reference.

| Symbol | Final equity | Net profit | Return % | Trades | Win rate % | Profit factor | Max DD % | Max recovery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| XAUUSD | 1000.00 | 0.00 | 0.00 | 0 | 0.00 | n/a | 0.00 | 0 |
| USDJPY | 880.13 | -119.87 | -11.99 | 749 | 27.90 | 0.298 | 12.03 | 3 |
| GBPUSD | 879.82 | -120.18 | -12.02 | 311 | 21.22 | 0.22 | 12.02 | 3 |
| EURJPY | 879.61 | -120.39 | -12.04 | 294 | 17.01 | 0.093 | 12.04 | 3 |
| EURUSD | 879.46 | -120.54 | -12.05 | 656 | 28.51 | 0.32 | 12.07 | 3 |

## Interpretation

- Default EA settings were used unless noted in metadata.
- JPY cross PnL that is not USDJPY is converted with the configured JPY/USD reference rate.
- Results include real spread from bid/ask ticks, but not BazarnForex slippage, rejected orders, swaps, or broker-specific stop/freeze behavior.
