# FX SMC Paper Robot Backtest Report

Generated UTC: 2026-07-01T13:16:21+00:00

## Scope

- Robot type: SMC-style liquidity sweep/reclaim paper robot
- Market: major FX pairs
- Pairs: EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD
- Data source: Yahoo Chart 1h OHLC bars
- Backtest window: 3 months
- Risk model: 1.00% paper account risk per trade
- Live trading: disabled; no broker integration or live order placement

## Selected Profile

The script ran a small in-sample parameter search and selected:

- Profile: `smc_lq_lb24_rr2_h12_s0.74`
- Liquidity lookback: 24 bars
- Risk/reward target: 2.0:1
- Maximum hold: 12 bars
- Minimum signal score: 0.74
- Session filter: 06:00-17:00 UTC

## Portfolio Result

| Metric | Result |
|--------|--------|
| Trades | 181 |
| Win rate | 44.2% |
| Net R | 19.69R |
| Average R/trade | 0.109R |
| Profit factor | 1.20 |
| Return at 1% risk | 19.86% |
| Max drawdown | 15.41% |

## Pair Breakdown

| Pair | Bars | Trades | Win Rate | Net R | Return | Max DD | Profit Factor |
|------|------|--------|----------|-------|--------|--------|---------------|
| EURUSD | 1542 | 17 | 35.3% | -0.83R | -0.95% | 5.57% | 0.92 |
| GBPUSD | 1542 | 28 | 42.9% | -0.97R | -1.17% | 4.14% | 0.94 |
| USDJPY | 1533 | 30 | 46.7% | 6.94R | 6.87% | 4.16% | 1.42 |
| USDCHF | 1533 | 34 | 38.2% | -1.22R | -1.49% | 10.28% | 0.94 |
| USDCAD | 1543 | 33 | 51.5% | 8.57R | 8.64% | 3.72% | 1.55 |
| AUDUSD | 1542 | 18 | 55.6% | 7.47R | 7.55% | 3.98% | 1.91 |
| NZDUSD | 1542 | 21 | 38.1% | -0.27R | -0.45% | 9.84% | 0.98 |

## Interpretation

The optimized portfolio was profitable over this three-month in-sample window, but the edge was not uniform across pairs. USDJPY, USDCAD, and AUDUSD carried most of the profit. EURUSD, GBPUSD, USDCHF, and NZDUSD were flat to negative and should not be enabled blindly without further validation.

## Validation Notes

- The generated full report is available locally at `reports/fx_trading/fx_smc_robot_backtest.md`.
- The generated machine-readable output is available locally at `reports/fx_trading/fx_smc_robot_backtest.json`.
- `reports/` is ignored by git in this repository, so this summary captures the committed result.
- Command used:

```bash
python3 scripts/fx_smc_robot_backtest.py --months 3 --interval 1h --optimize
```

## Risk Notice

This is research and paper-trading infrastructure only. Historical backtests, especially optimized in-sample results, do not guarantee future profitability and are not financial advice.
